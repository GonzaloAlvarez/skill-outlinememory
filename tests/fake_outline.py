"""An in-memory stand-in for the parts of the Outline API that outline-memory uses.

Scenarios: default · existing_root · existing_parent_with_child · dup_parent ·
no_collection · unauthorized · html_404 · foreign_tree · admin_user
"""
import json
import secrets
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

COLLECTION = "Memories"


def _node(title, text=""):
    nid = str(uuid.uuid4())
    return {"id": nid, "title": title, "url": "/doc/%s-%s" % (title.lower().replace(" ", "-")[:20], nid[:8]),
            "children": [], "_text": text, "_parent": None}


class FakeOutline:
    def __init__(self, scenario="default"):
        self.scenario = scenario
        self.token = "ol_api_" + secrets.token_hex(19)
        self.writes = []
        self.docs = {}
        self.collections = []
        self.tree = {}
        self._seed()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_class())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    # ── setup ──
    def _seed(self):
        name = "Other" if self.scenario == "no_collection" else COLLECTION
        cid = str(uuid.uuid4())
        self.collections.append({"id": cid, "name": name})
        self.collection_id = cid
        self.tree[cid] = []
        s = self.scenario
        if s in ("existing_root", "existing_parent_with_child", "dup_parent"):
            root = self.add(cid, "dev")
            if s == "dup_parent":
                self.add(cid, "dev")
            if s == "existing_parent_with_child":
                proj = self.add(cid, "my-service", parent=root)
                self.add(cid, "2026-01-01 Existing topic", parent=proj, text="old body")
        if s == "foreign_tree":
            personal = self.add(cid, "personal")
            travel = self.add(cid, "travel", parent=personal)
            self.add(cid, "Trip", parent=travel, text="trip notes")

    def add(self, cid, title, parent=None, text=""):
        node = _node(title, text)
        node["_parent"] = parent["id"] if parent else None
        (parent["children"] if parent else self.tree[cid]).append(node)
        self.docs[node["id"]] = (node, cid)
        return node

    def start(self):
        self.thread.start()
        return "http://127.0.0.1:%d" % self.server.server_address[1]

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def public_tree(self, cid=None):
        def strip(nodes):
            return [{"id": n["id"], "title": n["title"], "url": n["url"], "children": strip(n["children"])} for n in nodes]
        return strip(self.tree[cid or self.collection_id])

    # ── request handling ──
    def _handler_class(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, status, body, ctype="application/json"):
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if fake.scenario == "html_404":
                    return self._send(404, b"<!doctype html><html><body>not here</body></html>", "text/html")
                if self.path == "/_health":
                    return self._send(200, b"OK", "text/plain")
                if self.path == "/__state":
                    return self._send(200, {"writes": fake.writes, "tree": fake.public_tree()})
                self._send(404, {"ok": False, "error": "not_found"})

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                if fake.scenario == "html_404":
                    return self._send(404, b"<!doctype html><html><body>not here</body></html>", "text/html")
                if not self.path.startswith("/api/"):
                    return self._send(404, {"ok": False, "error": "not_found"})
                if self.headers.get("Authorization") != "Bearer " + fake.token or fake.scenario == "unauthorized":
                    return self._send(401, {"ok": False, "error": "authentication_required", "status": 401,
                                            "message": "Authentication required"})
                try:
                    payload = json.loads(raw.decode() or "{}")
                except ValueError:
                    return self._send(400, {"ok": False, "error": "validation_error", "message": "bad json"})
                method = self.path[len("/api/"):]
                handler = getattr(self, "m_" + method.replace(".", "_"), None)
                if handler is None:
                    return self._send(403, {"ok": False, "error": "authorization_error", "status": 403,
                                            "message": "Authorization error"})
                handler(payload)

            def m_auth_info(self, p):
                role = "admin" if fake.scenario == "admin_user" else "member"
                self._send(200, {"ok": True, "data": {"user": {"id": "u1", "name": "Agent (service identity)", "role": role}}})

            def m_collections_list(self, p):
                self._send(200, {"ok": True, "data": fake.collections})

            def m_collections_documents(self, p):
                cid = p.get("id")
                if cid not in fake.tree:
                    return self._send(404, {"ok": False, "error": "not_found", "message": "collection not found"})
                self._send(200, {"ok": True, "data": fake.public_tree(cid)})

            def m_documents_create(self, p):
                title = p.get("title")
                cid, pid = p.get("collectionId"), p.get("parentDocumentId")
                if not title or not (cid or pid):
                    return self._send(400, {"ok": False, "error": "validation_error",
                                            "message": "collectionId or parentDocumentId is required to publish"})
                parent = None
                if pid:
                    if pid not in fake.docs:
                        return self._send(404, {"ok": False, "error": "not_found", "message": "parent not found"})
                    parent, cid = fake.docs[pid][0], fake.docs[pid][1]
                node = fake.add(cid, title, parent=parent, text=p.get("text") or "")
                fake.writes.append({"method": "documents.create", "title": title, "parentDocumentId": pid,
                                    "collectionId": cid, "text": p.get("text") or "", "id": node["id"]})
                self._send(200, {"ok": True, "data": {"id": node["id"], "url": node["url"], "urlId": node["id"][:10],
                                                      "title": title, "parentDocumentId": pid, "collectionId": cid,
                                                      "text": p.get("text") or ""}})

            def m_documents_info(self, p):
                did = p.get("id")
                if did not in fake.docs:
                    return self._send(404, {"ok": False, "error": "not_found", "message": "document not found"})
                node, cid = fake.docs[did]
                self._send(200, {"ok": True, "data": {"id": node["id"], "title": node["title"], "url": node["url"],
                                                      "text": node["_text"], "parentDocumentId": node["_parent"],
                                                      "collectionId": cid}})

        return Handler


if __name__ == "__main__":  # manual poking: python3 tests/fake_outline.py [scenario]
    import sys
    import time
    f = FakeOutline(sys.argv[1] if len(sys.argv) > 1 else "default")
    print("url:", f.start())
    print("token:", f.token)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        f.stop()
