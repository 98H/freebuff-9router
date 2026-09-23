#!/usr/bin/env python3
"""
9Router Web UI Patcher for FreeBuff (freebucks-proxy)
=====================================================
Transforms the generic compatible provider form in 9Router into a senior
Product Designer grade interface for FreeBuff:
1. Provider Logo routing (/providers/freebuff.png) on detail page header.
2. "Add FreeBuff Account" modal title instead of "Add API Key".
3. "FreeBuff Auth Token" field label instead of "API Key".
4. Clean placeholder ("Paste FreeBuff auth token...").
5. Contextual name placeholder ("FreeBuff Account").
6. In-modal guidance card with clear token instructions.
7. "Test Connection" live probe integration button.
8. Suppression of the mandatory "Default Model" gate (which previously blocked saving).
9. Enable the "+ Add" connection button when accounts already exist.
10. "Auth Token" badge and "token" icon on connection cards.
11. Edit connection modal hint customization.

Guarantees:
- 100% idempotent: safely re-runnable after updates without duplicating hints.
- Syntax-checked via `node -c` after every modification; auto-rollback on syntax error.
"""

import os
import sys
import glob
import subprocess
import shutil

def find_build_dir():
    candidates = [
        os.path.expanduser("~/.local/lib/node_modules/9router/app/.next-cli-build"),
        "/usr/local/lib/node_modules/9router/app/.next-cli-build",
        "/usr/lib/node_modules/9router/app/.next-cli-build"
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return None

def verify_syntax(filepath):
    try:
        res = subprocess.run(["node", "-c", filepath], capture_output=True, text=True)
        if res.returncode != 0:
            print(f"  [!] Syntax error in {filepath}: {res.stderr}")
            return False
        return True
    except Exception as e:
        print(f"  [!] Node check error: {e}")
        return False

def patch_file(filepath, old_str, new_str, label):
    if not os.path.exists(filepath):
        print(f"  [-] File not found: {filepath}")
        return False
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    if new_str in content:
        # Already patched
        return True

    if old_str not in content:
        print(f"  [?] Target not found for {label} in {os.path.basename(filepath)}")
        return False

    backup_path = filepath + ".bak"
    shutil.copy2(filepath, backup_path)

    new_content = content.replace(old_str, new_str, 1)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)

    if not verify_syntax(filepath):
        print(f"  [!] Rolling back {label} due to syntax check failure!")
        shutil.copy2(backup_path, filepath)
        os.remove(backup_path)
        return False

    if os.path.exists(backup_path):
        os.remove(backup_path)

    print(f"  [+] Patched: {os.path.basename(filepath)} ({label})")
    return True

def run():
    print("==========================================================")
    print("  9Router High-Grade UI/UX Patcher for FreeBuff")
    print("==========================================================")

    build_dir = find_build_dir()
    if not build_dir:
        print("[!] 9Router build directory not found. Skipping UI patch.")
        return False

    print(f"Found 9Router build directory: {build_dir}\n")

    # 0. Ensure public asset exists
    asset_src = "/root/projects/freebuff-9router/assets/freebuff.png"
    asset_dst = os.path.join(os.path.dirname(build_dir), "public/providers/freebuff.png")
    if os.path.exists(asset_src):
        os.makedirs(os.path.dirname(asset_dst), exist_ok=True)
        shutil.copy2(asset_src, asset_dst)
        print(f"  [✓] Verified logo at {asset_dst}")

    # 0.1 Main Providers List page (/dashboard/providers)
    s_prov = os.path.join(build_dir, "server/app/(dashboard)/dashboard/providers/page.js")
    if os.path.exists(s_prov):
        patch_file(
            s_prov,
            'src:q&&b.apiType?',
            'src:b.id?.includes("freebuff")?"/providers/freebuff.png":q&&b.apiType?',
            "Server Providers List: logo routing"
        )
    for c_prov in glob.glob(os.path.join(build_dir, "static/chunks/app/(dashboard)/dashboard/providers/page-*.js")):
        patch_file(
            c_prov,
            'src:f&&t.apiType?',
            'src:t.id?.includes("freebuff")?"/providers/freebuff.png":f&&t.apiType?',
            "Client Providers List: logo routing"
        )

    # 1. Server Provider Detail Page
    s_detail = os.path.join(build_dir, "server/app/(dashboard)/dashboard/providers/[id]/page.js")
    if os.path.exists(s_detail):
        # Header logo routing
        patch_file(
            s_detail,
            'b5=()=>bp&&bh.apiType?',
            'b5=()=>bh.id?.includes("freebuff")?"/providers/freebuff.png":bp&&bh.apiType?',
            "Server: header logo"
        )
        # Enable "+ Add" button when connections exist
        patch_file(
            s_detail,
            'b1,!br&&(0,d.jsxs)("div",{className:"mt-4 grid grid-cols-1 gap-2 sm:flex",children:[',
            'b1,(!br||bh.id?.includes("freebuff"))&&(0,d.jsxs)("div",{className:"mt-4 grid grid-cols-1 gap-2 sm:flex",children:[',
            "Server: show Add button when connections exist"
        )
        # Header Add button label
        patch_file(
            s_detail,
            'onClick:()=>{X(""),V(!0)},className:"w-full sm:w-auto",children:"Add API Key"',
            'onClick:()=>{X(""),V(!0)},className:"w-full sm:w-auto",children:"Add"',
            "Server: header Add button label"
        )
        # Modal title
        patch_file(
            s_detail,
            'title:`Add ${c||b} ${w}`',
            'title:b?.includes("freebuff")?"Add FreeBuff Account":`Add ${c||b} ${w}`',
            "Server: modal title"
        )
        # Field label w
        patch_file(
            s_detail,
            'w=u?"Cookie Value":"qoder"===b||"qoder-cn"===b?"Personal Access Token (PAT)":"API Key"',
            'w=b?.includes("freebuff")?"FreeBuff Auth Token":u?"Cookie Value":"qoder"===b||"qoder-cn"===b?"Personal Access Token (PAT)":"API Key"',
            "Server: field label"
        )
        # Name placeholder
        patch_file(
            s_detail,
            'placeholder:t?"Ollama Local":"Production Key"',
            'placeholder:b?.includes("freebuff")?"FreeBuff Account":t?"Ollama Local":"Production Key"',
            "Server: name placeholder"
        )
        # Key placeholder
        patch_file(
            s_detail,
            'placeholder:u?"grok-web"===b?',
            'placeholder:b?.includes("freebuff")?"Paste FreeBuff auth token...":u?"grok-web"===b?',
            "Server: key placeholder"
        )
        # Hide Default Model field
        patch_file(
            s_detail,
            'f&&(0,d.jsx)(k.pd,{label:"Default Model"',
            'f&&!("openai-compatible-chat-freebuff"===b||"freebuff"===b||b?.includes("freebuff"))&&(0,d.jsx)(k.pd,{label:"Default Model"',
            "Server: hide Default Model field"
        )
        # Lift Default Model disabled gate on Save button
        patch_file(
            s_detail,
            'f&&!B.defaultModel.trim()',
            'f&&!("openai-compatible-chat-freebuff"===b||"freebuff"===b||b?.includes("freebuff"))&&!B.defaultModel.trim()',
            "Server: lift Default Model disabled gate"
        )
        # Lift Default Model gate on submit handler
        patch_file(
            s_detail,
            '(!f||B.defaultModel.trim())',
            '(!f||"openai-compatible-chat-freebuff"===b||"freebuff"===b||b?.includes("freebuff")||B.defaultModel.trim())',
            "Server: lift Default Model submit gate"
        )
        # Name optional in Add Account modal
        patch_file(
            s_detail,
            '!t&&(!B.name||!B.apiKey)',
            '!t&&(!(B.name||b?.includes("freebuff"))||!B.apiKey)',
            "Server: name optional on Save disabled"
        )
        patch_file(
            s_detail,
            '(t||B.name)',
            '(t||b?.includes("freebuff")||B.name)',
            "Server: name optional on submit check"
        )
        patch_file(
            s_detail,
            'name:B.name||(t?"Ollama Local":"")',
            'name:B.name||(b?.includes("freebuff")?"FreeBuff Account":t?"Ollama Local":"")',
            "Server: name default fallback"
        )
        # Test Connection button label
        patch_file(
            s_detail,
            'children:L?"Checking...":"Check"',
            'children:L?"Testing...":b?.includes("freebuff")?"Test Connection":"Check"',
            "Server: test button label"
        )
        # In-modal guidance card
        hint_s = ',("openai-compatible-chat-freebuff"===b||"freebuff"===b||b?.includes("freebuff"))&&(0,d.jsx)("p",{className:"text-xs text-brand-600 dark:text-brand-400 bg-brand-500/10 border border-brand-500/20 p-2.5 rounded-lg mt-1 font-sans leading-relaxed break-words",children:"💡 Where to get token: In terminal run `python3 /root/projects/freebuff-9router/freebuff9r.py login-url` to log in via browser, or copy authToken from ~/.codebuff/auth.json. Paste token above and click \'Test Connection\' before saving."})'
        anchor_s = 'v&&(0,d.jsx)("p",{className:"text-xs text-text-muted",children:"Use a direct xAI API key from console.x.ai. This is separate from Grok Build OAuth."})'
        if hint_s not in open(s_detail, "r").read():
            patch_file(s_detail, anchor_s, anchor_s + hint_s, "Server: guidance card")
        # Connection card badge & icon
        patch_file(
            s_detail,
            'a?.provider?.includes("qwen")||"openai-compatible-chat-chatgpt"===a?.provider||"openai-compatible-chat-qwen"===a?.provider)?"Session Token":"API Key"',
            'a?.provider?.includes("freebuff")||"openai-compatible-chat-freebuff"===a?.provider||a?.provider?.includes("qwen")||"openai-compatible-chat-chatgpt"===a?.provider||"openai-compatible-chat-qwen"===a?.provider)?"Auth Token":"API Key"',
            "Server: connection badge"
        )
        patch_file(
            s_detail,
            'a?.provider?.includes("qwen")||"openai-compatible-chat-chatgpt"===a?.provider||"openai-compatible-chat-qwen"===a?.provider)?"Session Account":"API Key"',
            'a?.provider?.includes("freebuff")||"openai-compatible-chat-freebuff"===a?.provider||a?.provider?.includes("qwen")||"openai-compatible-chat-chatgpt"===a?.provider||"openai-compatible-chat-qwen"===a?.provider)?"Auth Account":"API Key"',
            "Server: connection fallback name"
        )
        patch_file(
            s_detail,
            'children:L?"cookie":K?"lock":(a?.provider?.includes("chatgpt")||a?.provider?.includes("qwen")||"openai-compatible-chat-chatgpt"===a?.provider||"openai-compatible-chat-qwen"===a?.provider)?"token":"key"',
            'children:L?"cookie":K?"lock":(a?.provider?.includes("freebuff")||"openai-compatible-chat-freebuff"===a?.provider||a?.provider?.includes("chatgpt")||a?.provider?.includes("qwen")||"openai-compatible-chat-chatgpt"===a?.provider||"openai-compatible-chat-qwen"===a?.provider)?"token":"key"',
            "Server: connection icon"
        )

    # 2. Client Provider Detail Page
    c_dir = os.path.join(build_dir, "static/chunks/app/(dashboard)/dashboard/providers/[id]")
    if os.path.isdir(c_dir):
        c_files = [os.path.join(c_dir, f) for f in os.listdir(c_dir) if f.startswith("page-") and f.endswith(".js")]
        for c_detail in c_files:
            # Header logo routing
            patch_file(
                c_detail,
                't7=()=>tg&&td.apiType?',
                't7=()=>td.id?.includes("freebuff")?"/providers/freebuff.png":tg&&td.apiType?',
                "Client: header logo"
            )
            # Enable "+ Add" button when connections exist
            patch_file(
                c_detail,
                't5,!tb&&(0,i.jsxs)("div",{className:"mt-4 grid grid-cols-1 gap-2 sm:flex",children:[',
                't5,(!tb||td.id?.includes("freebuff"))&&(0,i.jsxs)("div",{className:"mt-4 grid grid-cols-1 gap-2 sm:flex",children:[',
                "Client: show Add button when connections exist"
            )
            # Header Add button label
            patch_file(
                c_detail,
                '(0,i.jsx)(c.$n,{size:"sm",icon:"add",onClick:()=>{V(""),G(!0)},className:"w-full sm:w-auto",children:"Add API Key"})',
                '(0,i.jsx)(c.$n,{size:"sm",icon:"add",onClick:()=>{V(""),G(!0)},className:"w-full sm:w-auto",children:"Add"})',
                "Client: header Add button label"
            )
            # Modal title
            patch_file(
                c_detail,
                'title:`Add ${s||t} ${w}`',
                'title:t?.includes("freebuff")?"Add FreeBuff Account":`Add ${s||t} ${w}`',
                "Client: modal title"
            )
            # Field label w
            patch_file(
                c_detail,
                'w=v?"Cookie Value":"qoder"===t||"qoder-cn"===t?"Personal Access Token (PAT)":"API Key"',
                'w=t?.includes("freebuff")?"FreeBuff Auth Token":v?"Cookie Value":"qoder"===t||"qoder-cn"===t?"Personal Access Token (PAT)":"API Key"',
                "Client: field label"
            )
            # Name placeholder
            patch_file(
                c_detail,
                'placeholder:b?"Ollama Local":"Production Key"',
                'placeholder:t?.includes("freebuff")?"FreeBuff Account":b?"Ollama Local":"Production Key"',
                "Client: name placeholder"
            )
            # Key placeholder
            patch_file(
                c_detail,
                'placeholder:v?"grok-web"===t?',
                'placeholder:t?.includes("freebuff")?"Paste FreeBuff auth token...":v?"grok-web"===t?',
                "Client: key placeholder"
            )
            # Hide Default Model field
            patch_file(
                c_detail,
                'l&&(0,i.jsx)(c.pd,{label:"Default Model"',
                'l&&!("openai-compatible-chat-freebuff"===t||"freebuff"===t||t?.includes("freebuff"))&&(0,i.jsx)(c.pd,{label:"Default Model"',
                "Client: hide Default Model field"
            )
            # Lift Default Model disabled gate on Save button
            patch_file(
                c_detail,
                'l&&!A.defaultModel.trim()',
                'l&&!("openai-compatible-chat-freebuff"===t||"freebuff"===t||t?.includes("freebuff"))&&!A.defaultModel.trim()',
                "Client: lift Default Model disabled gate"
            )
            # Lift Default Model gate on submit handler
            patch_file(
                c_detail,
                '(!l||A.defaultModel.trim())',
                '(!l||"openai-compatible-chat-freebuff"===t||"freebuff"===t||t?.includes("freebuff")||A.defaultModel.trim())',
                "Client: lift Default Model submit gate"
            )
            # Name optional in Add Account modal
            patch_file(
                c_detail,
                '!b&&(!A.name||!A.apiKey)',
                '!b&&(!(A.name||t?.includes("freebuff"))||!A.apiKey)',
                "Client: name optional on Save disabled"
            )
            patch_file(
                c_detail,
                '(b||A.name)',
                '(b||t?.includes("freebuff")||A.name)',
                "Client: name optional on submit check"
            )
            patch_file(
                c_detail,
                'name:A.name||(b?"Ollama Local":"")',
                'name:A.name||(t?.includes("freebuff")?"FreeBuff Account":b?"Ollama Local":"")',
                "Client: name default fallback"
            )
            # Test Connection button label
            patch_file(
                c_detail,
                'children:R?"Checking...":"Check"',
                'children:R?"Testing...":t?.includes("freebuff")?"Test Connection":"Check"',
                "Client: test button label"
            )
            # In-modal guidance card
            hint_c = ',("openai-compatible-chat-freebuff"===t||"freebuff"===t||t?.includes("freebuff"))&&(0,i.jsx)("p",{className:"text-xs text-brand-600 dark:text-brand-400 bg-brand-500/10 border border-brand-500/20 p-2.5 rounded-lg mt-1 font-sans leading-relaxed break-words",children:"💡 Where to get token: In terminal run `python3 /root/projects/freebuff-9router/freebuff9r.py login-url` to log in via browser, or copy authToken from ~/.codebuff/auth.json. Paste token above and click \'Test Connection\' before saving."})'
            anchor_c = 'j&&(0,i.jsx)("p",{className:"text-xs text-text-muted",children:"Use a direct xAI API key from console.x.ai. This is separate from Grok Build OAuth."})'
            if hint_c not in open(c_detail, "r").read():
                patch_file(c_detail, anchor_c, anchor_c + hint_c, "Client: guidance card")
            # Connection card badge & icon
            patch_file(
                c_detail,
                'size:"sm",children:_?"OAuth":q?"Cookie":"API Key"',
                'size:"sm",children:_?"OAuth":q?"Cookie":(e?.provider?.includes("freebuff")||"openai-compatible-chat-freebuff"===e?.provider)?"Auth Token":"API Key"',
                "Client: connection badge"
            )
            patch_file(
                c_detail,
                'children:q?"cookie":_?"lock":"key"',
                'children:q?"cookie":_?"lock":(e?.provider?.includes("freebuff")||"openai-compatible-chat-freebuff"===e?.provider)?"token":"key"',
                "Client: connection icon"
            )
            patch_file(
                c_detail,
                '||(_?"OAuth Account":q?"Cookie Account":"API Key")',
                '||(_?"OAuth Account":q?"Cookie Account":(e?.provider?.includes("freebuff")||"openai-compatible-chat-freebuff"===e?.provider)?"Auth Account":"API Key")',
                "Client: connection fallback name"
            )

    # 3. EditConnectionModal chunks
    chunk_412 = os.path.join(build_dir, "server/chunks/412.js")
    if os.path.exists(chunk_412):
        patch_file(
            chunk_412,
            'hint:"Leave blank to keep the current API key."',
            'hint:b?.provider?.includes("freebuff")?"Leave blank to keep the current auth token.":"Leave blank to keep the current API key."',
            "Server: edit modal hint"
        )
        patch_file(
            chunk_412,
            'label:"API Key",type:"password",value:o.apiKey',
            'label:b?.provider?.includes("freebuff")?"FreeBuff Auth Token":"API Key",type:"password",value:o.apiKey',
            "Server: edit modal label"
        )
        patch_file(
            chunk_412,
            'children:A?"Checking...":"Check"',
            'children:A?"Testing...":b?.provider?.includes("freebuff")?"Test Connection":"Check"',
            "Server: edit modal test button"
        )

    for mc in glob.glob(os.path.join(build_dir, "static/chunks/5497-*.js")):
        patch_file(
            mc,
            'hint:"Leave blank to keep the current API key."',
            'hint:t?.provider?.includes("freebuff")?"Leave blank to keep the current auth token.":"Leave blank to keep the current API key."',
            "Client: edit modal hint"
        )
        patch_file(
            mc,
            'label:"API Key",type:"password",value:p.apiKey',
            'label:t?.provider?.includes("freebuff")?"FreeBuff Auth Token":"API Key",type:"password",value:p.apiKey',
            "Client: edit modal label"
        )
        patch_file(
            mc,
            'children:S?"Checking...":"Check"',
            'children:S?"Testing...":t?.provider?.includes("freebuff")?"Test Connection":"Check"',
            "Client: edit modal test button"
        )

    print("\n[✓] FreeBuff UI/UX patching completed successfully.")
    return True

if __name__ == "__main__":
    success = run()
    sys.exit(0 if success else 1)
