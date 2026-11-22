#!/usr/bin/env python3
"""
Antigravity IDE & 2.0 Chat Sync Utility
---------------------------------------
Exports, imports, and synchronizes conversations for Antigravity IDE projects
between machines (e.g. iMac and MacBook), including support for renamed and moved folders.

Zero external dependencies - uses standard Python 3 libraries.
"""

import os
import sys
import json
import sqlite3
import shutil
import base64
import argparse
import pathlib
import urllib.parse
from datetime import datetime, timezone

# Default paths
GEMINI_DIR = os.path.expanduser("~/.gemini/antigravity")
CONVERSATIONS_DIR = os.path.join(GEMINI_DIR, "conversations")
BRAIN_DIR = os.path.join(GEMINI_DIR, "brain")
SUMMARIES_DB = os.path.join(GEMINI_DIR, "conversation_summaries.db")


def serialize_val(val):
    """Serialize a database value into JSON-compatible format."""
    if isinstance(val, (bytes, bytearray, memoryview)):
        return {"__b64__": base64.b64encode(bytes(val)).decode("ascii")}
    return val


def deserialize_val(val):
    """Deserialize a JSON value back into database value."""
    if isinstance(val, dict) and "__b64__" in val:
        return base64.b64decode(val["__b64__"])
    return val


def encode_varint(n: int) -> bytes:
    """Encode an integer as a protobuf varint."""
    res = bytearray()
    while n > 0x7F:
        res.append((n & 0x7F) | 0x80)
        n >>= 7
    res.append(n & 0x7F)
    return bytes(res)


def replace_protobuf_uri(blob: bytes, old_uri: str, new_uri: str) -> bytes:
    """
    Safely replace a file:// URI inside a protobuf blob, updating
    the preceding varint string-length prefix if lengths differ.
    """
    old_b = old_uri.encode("utf-8")
    new_b = new_uri.encode("utf-8")
    if old_b not in blob:
        return blob
    if len(old_b) == len(new_b):
        return blob.replace(old_b, new_b)

    old_len = len(old_b)
    old_vlen = encode_varint(old_len)
    new_vlen = encode_varint(len(new_b))

    result = bytearray()
    idx = 0
    while True:
        pos = blob.find(old_b, idx)
        if pos == -1:
            result.extend(blob[idx:])
            break
        vlen_len = len(old_vlen)
        if pos >= vlen_len and blob[pos - vlen_len : pos] == old_vlen:
            result.extend(blob[idx : pos - vlen_len])
            result.extend(new_vlen)
            result.extend(new_b)
            idx = pos + old_len
        else:
            result.extend(blob[idx : pos + old_len])
            idx = pos + old_len
    return bytes(result)


def get_project_uri(project_dir: str) -> str:
    """Convert local project directory to Antigravity's workspace URI format."""
    return pathlib.Path(project_dir).resolve().as_uri()


def ensure_gemini_dirs():
    """Ensure ~/.gemini/antigravity subdirectories exist."""
    os.makedirs(CONVERSATIONS_DIR, exist_ok=True)
    os.makedirs(BRAIN_DIR, exist_ok=True)


def list_conversations(project_dir: str, as_json: bool = False):
    """List all conversations belonging to the given project."""
    target_uri = get_project_uri(project_dir)

    if not os.path.exists(SUMMARIES_DB):
        if as_json:
            print(json.dumps({"status": "error", "message": f"No database found at {SUMMARIES_DB}", "conversations": []}))
        else:
            print(f"No summaries database found at {SUMMARIES_DB}")
        return []

    conn = sqlite3.connect(SUMMARIES_DB)
    c = conn.cursor()
    c.execute(
        "SELECT conversation_id, title, step_count, last_modified_time, workspace_uris FROM conversation_summaries"
    )
    rows = c.fetchall()
    conn.close()

    matched = []
    for cid, title, steps, lmt, uris_raw in rows:
        try:
            uris = json.loads(uris_raw)
        except Exception:
            uris = [uris_raw]
        if any(target_uri.rstrip("/") in u.rstrip("/") for u in uris):
            matched.append({
                "conversation_id": cid,
                "title": title or "(Untitled conversation)",
                "step_count": steps,
                "last_modified_time": str(lmt),
                "workspace_uris": uris
            })

    if as_json:
        print(json.dumps({
            "status": "ok",
            "project_path": project_dir,
            "project_uri": target_uri,
            "count": len(matched),
            "conversations": matched
        }, ensure_ascii=False, indent=2))
        return matched

    print(f"Project path: {project_dir}")
    print(f"Project URI:  {target_uri}\n")
    if not matched:
        print("No conversations found for this project in local Antigravity store.")
    else:
        print(f"Found {len(matched)} conversation(s) for this project:")
        print("-" * 85)
        print(f"{'ID':<38} | {'Steps':<5} | {'Last Modified':<20} | {'Title'}")
        print("-" * 85)
        for m in matched:
            print(f"{m['conversation_id']:<38} | {m['step_count']:<5} | {str(m['last_modified_time'])[:19]:<20} | {m['title']}")
        print("-" * 85)

    return matched


def safe_sqlite_backup(src_path: str, dst_path: str):
    """Safely backup an active SQLite database using online backup API (flushes WAL)."""
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    if os.path.exists(dst_path):
        os.remove(dst_path)
    src_conn = sqlite3.connect(src_path)
    dst_conn = sqlite3.connect(dst_path)
    src_conn.backup(dst_conn)
    dst_conn.close()
    src_conn.close()


def export_readable_markdown(cid: str, title: str, out_md_path: str):
    """Export conversation transcript to readable markdown if available."""
    transcript_path = os.path.join(BRAIN_DIR, cid, ".system_generated", "logs", "transcript.jsonl")
    if not os.path.exists(transcript_path):
        return

    os.makedirs(os.path.dirname(out_md_path), exist_ok=True)
    with open(transcript_path, "r", encoding="utf-8") as f_in, open(out_md_path, "w", encoding="utf-8") as f_out:
        f_out.write(f"# {title}\n\n")
        f_out.write(f"**Conversation ID:** `{cid}`  \n")
        f_out.write(f"**Exported At:** `{datetime.now(timezone.utc).isoformat()}`\n\n---\n\n")

        for line in f_in:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                stype = entry.get("type", "")
                content = entry.get("content", "")
                if stype == "USER_INPUT":
                    f_out.write(f"### 👤 User\n\n{content}\n\n---\n\n")
                elif stype in ("MODEL_RESPONSE", "PLANNER_RESPONSE", "GENERIC") and content:
                    f_out.write(f"### 🤖 Gemini\n\n{content}\n\n---\n\n")
            except Exception:
                pass


def export_chats(project_dir: str, export_dir: str, all_chats: bool = False, as_json: bool = False):
    """Export conversations to export_dir."""
    target_uri = get_project_uri(project_dir)
    os.makedirs(export_dir, exist_ok=True)

    if not os.path.exists(SUMMARIES_DB):
        msg = f"Error: Summaries database not found at {SUMMARIES_DB}"
        if as_json:
            print(json.dumps({"status": "error", "message": msg}))
        else:
            print(msg)
        return False

    conn = sqlite3.connect(SUMMARIES_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM conversation_summaries")
    all_rows = [dict(row) for row in c.fetchall()]

    # Filter
    target_rows = []
    for r in all_rows:
        uris_raw = r.get("workspace_uris", "[]")
        try:
            uris = json.loads(uris_raw)
        except Exception:
            uris = [uris_raw]
        if all_chats or any(target_uri.rstrip("/") in u.rstrip("/") for u in uris):
            target_rows.append(r)

    if not target_rows:
        msg = "No conversations found for this project."
        if as_json:
            print(json.dumps({"status": "warning", "message": msg, "exported_count": 0}))
        else:
            print(msg)
        conn.close()
        return False

    if not as_json:
        print(f"Exporting {len(target_rows)} conversation(s) to:\n  {export_dir}\n")

    manifest_conversations = []
    for r in target_rows:
        cid = r["conversation_id"]
        title = r.get("title", "") or cid

        # Serialize row values (e.g. blobs to base64)
        row_dict = {}
        for k, v in r.items():
            row_dict[k] = serialize_val(v)

        # Fetch FTS chunks
        c.execute("SELECT * FROM conversations_fts WHERE conversation_id = ?", (cid,))
        fts_rows = []
        for fts_row in c.fetchall():
            chunk_dict = {}
            for col_idx, col_name in enumerate(fts_row.keys()):
                chunk_dict[col_name] = serialize_val(fts_row[col_idx])
            fts_rows.append(chunk_dict)
        row_dict["fts_chunks"] = fts_rows

        # 1. Backup SQLite database
        src_db = os.path.join(CONVERSATIONS_DIR, f"{cid}.db")
        dst_db = os.path.join(export_dir, "conversations", f"{cid}.db")
        if os.path.exists(src_db):
            safe_sqlite_backup(src_db, dst_db)
            if not as_json:
                print(f"  [✓] Backed up DB: {cid[:8]}... ({title[:30]})")

        # 2. Copy brain folder if exists
        src_brain = os.path.join(BRAIN_DIR, cid)
        dst_brain = os.path.join(export_dir, "brain", cid)
        if os.path.exists(src_brain):
            if os.path.exists(dst_brain):
                shutil.rmtree(dst_brain)
            shutil.copytree(src_brain, dst_brain)
            if not as_json:
                print(f"  [✓] Copied brain artifacts: {cid[:8]}...")

        # 3. Export human-readable Markdown
        safe_title = "".join([ch if ch.isalnum() or ch in " ._-" else "_" for ch in title]).strip() or cid
        md_file = os.path.join(export_dir, "readable_transcripts", f"{safe_title}.md")
        export_readable_markdown(cid, title, md_file)

        manifest_conversations.append(row_dict)

    conn.close()

    # Save manifest metadata
    metadata = {
        "version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source_workspace_uri": target_uri,
        "conversations": manifest_conversations
    }
    manifest_path = os.path.join(export_dir, "metadata.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    if as_json:
        print(json.dumps({
            "status": "ok",
            "message": f"Successfully exported {len(manifest_conversations)} conversation(s).",
            "export_dir": export_dir,
            "exported_count": len(manifest_conversations)
        }, ensure_ascii=False, indent=2))
    else:
        print(f"\n[SUCCESS] Export complete! {len(manifest_conversations)} conversation(s) exported.")
    return True


def import_chats(project_dir: str, export_dir: str, as_json: bool = False):
    """Import conversations from export_dir into local Antigravity environment."""
    manifest_path = os.path.join(export_dir, "metadata.json")
    if not os.path.exists(manifest_path):
        msg = f"Error: Manifest metadata not found at {manifest_path}"
        if as_json:
            print(json.dumps({"status": "error", "message": msg}))
        else:
            print(msg)
        return False

    with open(manifest_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    source_uri = metadata.get("source_workspace_uri", "")
    target_uri = get_project_uri(project_dir)
    conversations = metadata.get("conversations", [])

    if not as_json:
        print(f"Source Workspace URI: {source_uri}")
        print(f"Target Workspace URI: {target_uri}")
        print(f"Importing {len(conversations)} conversation(s)...\n")

    ensure_gemini_dirs()

    # Connect to local summaries DB
    conn = sqlite3.connect(SUMMARIES_DB)
    c = conn.cursor()

    imported_count = 0
    for conv in conversations:
        cid = conv["conversation_id"]
        title = conv.get("title", "") or cid

        # 1. Restore conversations/<id>.db
        src_db = os.path.join(export_dir, "conversations", f"{cid}.db")
        dst_db = os.path.join(CONVERSATIONS_DIR, f"{cid}.db")
        if os.path.exists(src_db):
            safe_sqlite_backup(src_db, dst_db)
            if source_uri and source_uri != target_uri:
                try:
                    c_db = sqlite3.connect(dst_db)
                    cur = c_db.cursor()
                    cur.execute("SELECT data FROM trajectory_metadata_blob WHERE id = 'main'")
                    row = cur.fetchone()
                    if row and row[0]:
                        updated_traj = replace_protobuf_uri(row[0], source_uri, target_uri)
                        cur.execute("UPDATE trajectory_metadata_blob SET data = ? WHERE id = 'main'", (sqlite3.Binary(updated_traj),))
                        c_db.commit()
                    c_db.close()
                except Exception:
                    pass

        # 2. Restore brain/<id>
        src_brain = os.path.join(export_dir, "brain", cid)
        dst_brain = os.path.join(BRAIN_DIR, cid)
        if os.path.exists(src_brain):
            if os.path.exists(dst_brain):
                shutil.rmtree(dst_brain)
            shutil.copytree(src_brain, dst_brain)

        # 3. Adjust workspace URIs to match current machine and renamed directory
        orig_uris_raw = conv.get("workspace_uris", "[]")
        try:
            orig_uris = json.loads(orig_uris_raw)
            new_uris = [target_uri if (u == source_uri or source_uri in u) else u for u in orig_uris]
            if target_uri not in new_uris:
                new_uris.append(target_uri)
            conv["workspace_uris"] = json.dumps(new_uris, ensure_ascii=False)
        except Exception:
            conv["workspace_uris"] = json.dumps([target_uri], ensure_ascii=False)

        # 4. Adjust raw_summary protobuf blob
        raw_summary_bytes = None
        if "raw_summary" in conv:
            raw_summary_bytes = deserialize_val(conv["raw_summary"])
            if raw_summary_bytes and source_uri and source_uri != target_uri:
                raw_summary_bytes = replace_protobuf_uri(raw_summary_bytes, source_uri, target_uri)

        # 5. Insert/Update conversation_summaries
        c.execute("DELETE FROM conversation_summaries WHERE conversation_id = ?", (cid,))
        cols = [
            "conversation_id", "title", "preview", "step_count", "last_modified_time",
            "workspace_uris", "status", "source", "project_id", "agent_name",
            "parent_conversation_id", "nesting_depth", "battle_id",
            "winning_conversation_id", "not_fully_idle", "killed",
            "last_user_input_time", "last_user_input_step_index", "app_data_dir",
            "raw_summary", "group_id"
        ]
        values = []
        for col in cols:
            if col == "raw_summary":
                values.append(sqlite3.Binary(raw_summary_bytes) if raw_summary_bytes else None)
            else:
                val = conv.get(col, "")
                values.append(deserialize_val(val))
        
        placeholders = ", ".join(["?"] * len(cols))
        col_names = ", ".join([f"`{c}`" for c in cols])
        c.execute(f"INSERT INTO conversation_summaries ({col_names}) VALUES ({placeholders})", values)

        # 6. Restore FTS
        fts_chunks = conv.get("fts_chunks", [])
        if fts_chunks:
            c.execute("DELETE FROM conversations_fts WHERE conversation_id = ?", (cid,))
            for chunk in fts_chunks:
                ws = chunk.get("workspace", "")
                if ws == source_uri:
                    ws = target_uri
                c.execute("""
                    INSERT INTO conversations_fts (
                        conversation_id, chunk_index, chunk_first_step, chunk_last_step,
                        last_modified_time, step_count, last_step_created_at, archived,
                        user_step_byte_offsets, agent_step_byte_offsets, title,
                        workspace, project, user_body, agent_body
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    cid, chunk.get("chunk_index"), chunk.get("chunk_first_step"), chunk.get("chunk_last_step"),
                    chunk.get("last_modified_time"), chunk.get("step_count"), chunk.get("last_step_created_at"),
                    chunk.get("archived"),
                    deserialize_val(chunk.get("user_step_byte_offsets")),
                    deserialize_val(chunk.get("agent_step_byte_offsets")),
                    chunk.get("title"), ws, chunk.get("project"), chunk.get("user_body"), chunk.get("agent_body")
                ))

        imported_count += 1
        if not as_json:
            print(f"  [✓] Imported: {cid[:8]}... ({title[:30]})")

    conn.commit()
    conn.close()

    if as_json:
        print(json.dumps({
            "status": "ok",
            "message": f"Successfully imported {imported_count} conversation(s) into this project.",
            "imported_count": imported_count,
            "target_uri": target_uri
        }, ensure_ascii=False, indent=2))
    else:
        print(f"\n[SUCCESS] Import complete! {imported_count} conversation(s) restored into Antigravity IDE.")
    return True


def sync_chats(project_dir: str, export_dir: str, as_json: bool = False):
    """
    Two-way smart sync:
    - If export doesn't exist, exports local.
    - If local DB has newer modifications, exports.
    - If export metadata has newer modifications, imports.
    """
    manifest_path = os.path.join(export_dir, "metadata.json")
    if not os.path.exists(manifest_path):
        if not as_json:
            print("No export bundle found. Performing initial export...")
        return export_chats(project_dir, export_dir, as_json=as_json)

    with open(manifest_path, "r", encoding="utf-8") as f:
        export_meta = json.load(f)

    export_time_str = export_meta.get("exported_at", "")
    target_uri = get_project_uri(project_dir)

    # Check local max modified time
    conn = sqlite3.connect(SUMMARIES_DB)
    c = conn.cursor()
    c.execute("SELECT conversation_id, last_modified_time, workspace_uris FROM conversation_summaries")
    local_rows = c.fetchall()
    conn.close()

    local_matched_ids = set()
    latest_local_time = ""
    for cid, lmt, uris_raw in local_rows:
        try:
            uris = json.loads(uris_raw)
        except Exception:
            uris = [uris_raw]
        if any(target_uri.rstrip("/") in u.rstrip("/") for u in uris):
            local_matched_ids.add(cid)
            if str(lmt) > latest_local_time:
                latest_local_time = str(lmt)

    exported_cids = {c["conversation_id"] for c in export_meta.get("conversations", [])}

    if not as_json:
        print(f"Latest local modification:  {latest_local_time or 'None'}")
        print(f"Latest export timestamp:    {export_time_str}")

    # If local has conversations not in export or newer local timestamp -> export
    if latest_local_time > export_time_str or (local_matched_ids - exported_cids):
        if not as_json:
            print("\nAction: Local chats are newer. Running EXPORT...")
        return export_chats(project_dir, export_dir, as_json=as_json)
    else:
        if not as_json:
            print("\nAction: Exported chats are up to date or newer. Running IMPORT...")
        return import_chats(project_dir, export_dir, as_json=as_json)


def main():
    parser = argparse.ArgumentParser(description="Antigravity IDE Chat Export & Import Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    sub_list = subparsers.add_parser("list", help="List conversations for current or specified project")
    sub_list.add_argument("--dir", default=os.getcwd(), help="Project directory (default: current directory)")
    sub_list.add_argument("--json", action="store_true", help="Output results in JSON format")

    # export
    sub_exp = subparsers.add_parser("export", help="Export conversations for project")
    sub_exp.add_argument("--dir", default=os.getcwd(), help="Project directory")
    sub_exp.add_argument("--out", default="", help="Custom export folder (default: .antigravity_chats in project)")
    sub_exp.add_argument("--all", action="store_true", help="Export all conversations regardless of project")
    sub_exp.add_argument("--json", action="store_true", help="Output results in JSON format")

    # import
    sub_imp = subparsers.add_parser("import", help="Import conversations into Antigravity")
    sub_imp.add_argument("--dir", default=os.getcwd(), help="Project directory")
    sub_imp.add_argument("--from-dir", default="", help="Custom import folder (default: .antigravity_chats in project)")
    sub_imp.add_argument("--json", action="store_true", help="Output results in JSON format")

    # sync
    sub_sync = subparsers.add_parser("sync", help="Bidirectional smart sync between project and local Antigravity")
    sub_sync.add_argument("--dir", default=os.getcwd(), help="Project directory")
    sub_sync.add_argument("--bundle", default="", help="Custom bundle folder (default: .antigravity_chats in project)")
    sub_sync.add_argument("--json", action="store_true", help="Output results in JSON format")

    args = parser.parse_args()

    project_dir = os.path.abspath(args.dir)
    default_export_dir = os.path.join(project_dir, ".antigravity_chats")

    if args.command == "list":
        list_conversations(project_dir, as_json=args.json)
    elif args.command == "export":
        out_dir = os.path.abspath(args.out) if args.out else default_export_dir
        export_chats(project_dir, out_dir, all_chats=args.all, as_json=args.json)
    elif args.command == "import":
        from_dir = os.path.abspath(args.from_dir) if args.from_dir else default_export_dir
        import_chats(project_dir, from_dir, as_json=args.json)
    elif args.command == "sync":
        bundle_dir = os.path.abspath(args.bundle) if args.bundle else default_export_dir
        sync_chats(project_dir, bundle_dir, as_json=args.json)


if __name__ == "__main__":
    main()
