#!/usr/bin/env python3
"""
9Router Web UI Patcher for FreeBuff (and Web Bridges)
=====================================================
Transforms compatible provider forms into sleek native Antigravity-style
interfaces with:
1. Exact official provider logo (/providers/freebuff.png).
2. "Add FreeBuff Account" modal title instead of "Add API Key".
3. "FreeBuff CLI Token" field label instead of "API Key".
4. Clean box-fitting placeholders ("Paste FreeBuff token...").
5. In-modal Step-by-Step Guidance Card.
6. "Session Token" badges & "token" icons on connection cards.
7. "Test Connection" button instead of "Check".
8. Suppression of "Default Model: gpt-4o-mini" box.
9. Bypasses the clunky compatible form E so that models are displayed
   as interactive cards with toggles, tests, thinking badges, and "+ Add Model".
10. Dynamic live model discovery via useEffect.
"""

import os
import sys
import glob
import re

def find_9router_build_dir():
    candidates = [
        os.path.expanduser("~/.local/lib/node_modules/9router/app/.next-cli-build"),
        os.path.expanduser("~/.local/lib/node_modules/9router/app/.next"),
        "/usr/local/lib/node_modules/9router/app/.next-cli-build",
        "/usr/local/lib/node_modules/9router/app/.next",
        "/usr/lib/node_modules/9router/app/.next-cli-build",
        "/usr/lib/node_modules/9router/app/.next"
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return None

def patch_file(path, old_pattern, new_pattern, label=""):
    if not os.path.exists(path):
        return False
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if new_pattern in content:
        print(f"  [✓] Already patched: {os.path.basename(path)} {label}")
        return True

    if old_pattern not in content:
        print(f"  [!] Pattern not found in: {os.path.basename(path)} {label}")
        return False

    content = content.replace(old_pattern, new_pattern, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  [+] Applied patch: {os.path.basename(path)} {label}")
    return True

def inject_guidance_card(content: str, is_server: bool = False) -> str:
    if is_server:
        var = "b"
        jsx = "(0,d.jsx)"
        anchor = 'v&&(0,d.jsx)("p",{className:"text-xs text-text-muted",children:"Use a direct xAI API key from console.x.ai. This is separate from Grok Build OAuth."})'
    else:
        var = "t"
        jsx = "(0,i.jsx)"
        anchor = 'j&&(0,i.jsx)("p",{className:"text-xs text-text-muted",children:"Use a direct xAI API key from console.x.ai. This is separate from Grok Build OAuth."})'

    hint = (
        f',("openai-compatible-chat-freebuff"==={var}||"freebuff"==={var})&&{jsx}('
        f'"p",{{className:"text-xs text-brand-600 dark:text-brand-400 bg-brand-500/10 border border-brand-500/20 p-2.5 rounded-lg mt-1 font-sans leading-relaxed break-words",'
        f'children:"💡 Where to get token: Run \'python3 freebuff9r.py login-url\' or log in to codebuff.com → copy token. Click \'Test Connection\' before saving."}})'
    )

    if hint in content:
        return content

    pos = content.find(anchor)
    if pos == -1:
        return content

    insert_idx = pos + len(anchor)
    return content[:insert_idx] + hint + content[insert_idx:]

def run():
    print("==========================================================")
    print("  9Router High-Grade UX Patcher for FreeBuff Provider")
    print("==========================================================")

    build_dir = find_9router_build_dir()
    if not build_dir:
        print("[!] 9Router build directory not found.")
        sys.exit(1)

    print(f"Found 9Router build directory: {build_dir}\n")

    # 0. Copy logo asset if needed
    logo_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "freebuff.png")
    logo_dst = os.path.join(build_dir, "../public/providers/freebuff.png")
    if os.path.exists(logo_src) and not os.path.exists(logo_dst):
        import shutil
        os.makedirs(os.path.dirname(logo_dst), exist_ok=True)
        shutil.copy2(logo_src, logo_dst)
        print("  [+] Copied freebuff.png to public/providers/")

    # 1. Server chunks: Empty static catalog in 6070.js
    p_6070 = os.path.join(build_dir, "server/chunks/6070.js")
    if os.path.exists(p_6070):
        with open(p_6070, "r", encoding="utf-8") as f:
            c6070 = f.read()
        if 'q["freebuff"]' not in c6070:
            target = 'a["openrouter-tts-voices"]=m.openrouter.allVoices,a}())'
            if target in c6070:
                c6070 = c6070.replace(target, target + ',q["freebuff"]=q["openai-compatible-chat-freebuff"]=[]')
                with open(p_6070, "w", encoding="utf-8") as f:
                    f.write(c6070)
                print("  [+] Registered empty static catalog in 6070.js")

    # 2. Client chunks: Empty static catalog in 1321-*.js
    for p in glob.glob(os.path.join(build_dir, "static/chunks/1321-*.js")):
        with open(p, "r", encoding="utf-8") as f:
            c1321 = f.read()
        if 'l["freebuff"]' not in c1321 and 'm["freebuff"]' not in c1321:
            target = 'Object.assign(l,(0,r.pp)())'
            if target in c1321:
                c1321 = c1321.replace(target, target + ',l["freebuff"]=l["openai-compatible-chat-freebuff"]=[]')
                with open(p, "w", encoding="utf-8") as f:
                    f.write(c1321)
                print(f"  [+] Registered empty static catalog in {os.path.basename(p)}")

    # 3. Overview Page: /dashboard/providers (Logo routing)
    p_s_prov = os.path.join(build_dir, "server/app/(dashboard)/dashboard/providers/page.js")
    if os.path.exists(p_s_prov):
        with open(p_s_prov, "r", encoding="utf-8") as f:
            c_sprov = f.read()
        if 'b.id?.includes("freebuff")' not in c_sprov:
            # find logo routing
            c_sprov = re.sub(
                r'src:([^,}]+)apiType\?',
                r'src:b.id?.includes("freebuff")?"/providers/freebuff.png":\1apiType?',
                c_sprov,
                count=1
            )
            with open(p_s_prov, "w", encoding="utf-8") as f:
                f.write(c_sprov)
            print("  [+] Patched server overview provider logo")

    for p in glob.glob(os.path.join(build_dir, "static/chunks/app/(dashboard)/dashboard/providers/page-*.js")):
        with open(p, "r", encoding="utf-8") as f:
            c_cprov = f.read()
        if 't.id?.includes("freebuff")' not in c_cprov:
            c_cprov = re.sub(
                r'src:([^,}]+)apiType\?',
                r'src:t.id?.includes("freebuff")?"/providers/freebuff.png":\1apiType?',
                c_cprov,
                count=1
            )
            with open(p, "w", encoding="utf-8") as f:
                f.write(c_cprov)
            print(f"  [+] Patched client overview provider logo in {os.path.basename(p)}")

    # 4. Detail Page: /dashboard/providers/[id] (Client chunks)
    client_dir = glob.escape(os.path.join(build_dir, "static/chunks/app/(dashboard)/dashboard/providers/[id]"))
    for p in glob.glob(os.path.join(client_dir, "page-*.js")):
        with open(p, "r", encoding="utf-8") as f:
            c = f.read()

        # 4.1 Bypass compatible form E
        c = c.replace('if(tb)return(0,i.jsx)(E,', 'if(false)return(0,i.jsx)(E,')
        # 4.2 Enable tag list
        c = c.replace('!tb&&(e=[...th,', 'true&&(e=[...th,')
        # 4.3 Enable add modal
        c = c.replace('!tb&&(0,i.jsx)(K,{isOpen:ej,providerAlias:tN', 'true&&(0,i.jsx)(K,{isOpen:ej,providerAlias:tN')
        # 4.4 Enable dynamic model fetch in useEffect
        c = c.replace('if("cursor"!==f&&"zed"!==f)return void eK([]);', 'if("cursor"!==f&&"zed"!==f&&!tb)return void eK([]);')
        # 4.5 Dynamic model array
        c = c.replace('th=("cursor"===f||"zed"===f)&&eU.length>0?eU:tx', 'th=("cursor"===f||"zed"===f||tb)&&eU.length>0?eU:tx')

        # 4.6 Header Add button & Connection Add button
        c = c.replace('children:"Add API Key"', 'children:"Add"')
        c = c.replace('tb?"Add API Key":', 'tb?"Add":')

        # 4.7 Detail page header logo
        if 'td.id?.includes("freebuff")' not in c:
            c = c.replace('t7=()=>tg&&td.apiType?', 't7=()=>td.id?.includes("freebuff")?"/providers/freebuff.png":tg&&td.apiType?')

        # 4.8 Modal title & field label
        old_lbl = 'tw="xai"===f?"xAI API Key":"kimi"===f?"Kimi API Key":"qoder"===f||"qoder-cn"===f?"PAT":"API Key"'
        new_lbl = 'tw=f?.includes("freebuff")?"FreeBuff CLI Token":"xai"===f?"xAI API Key":"kimi"===f?"Kimi API Key":"qoder"===f||"qoder-cn"===f?"PAT":"API Key"'
        c = c.replace(old_lbl, new_lbl)

        # 4.9 Name placeholder
        old_name_ph = 'placeholder:b?"Ollama Local":"Production Key"'
        new_name_ph = 'placeholder:t?.includes("freebuff")?"FreeBuff Account":b?"Ollama Local":"Production Key"'
        c = c.replace(old_name_ph, new_name_ph)

        # 4.10 Input placeholder
        old_inp_ph = ':"qoder"===t||"qoder-cn"===t?"pt-...":""'
        new_inp_ph = ':"qoder"===t||"qoder-cn"===t?"pt-...":t?.includes("freebuff")?"Paste FreeBuff token...":""'
        c = c.replace(old_inp_ph, new_inp_ph)

        # 4.11 Test Connection button
        old_btn = 'children:R?"Checking...":"Check"'
        new_btn = 'children:R?"Testing...":(t?.includes("freebuff")?"Test Connection":"Check")'
        c = c.replace(old_btn, new_btn)

        # 4.12 Hide Default Model field for FreeBuff
        old_dm = 'l&&(0,i.jsx)(c.pd,{label:"Default Model"'
        new_dm = 'l&&!t?.includes("freebuff")&&(0,i.jsx)(c.pd,{label:"Default Model"'
        c = c.replace(old_dm, new_dm)

        # 4.13 Connection badge & icon
        old_badge = 'children:_?"OAuth":q?"Cookie":"API Key"'
        new_badge = 'children:_?"OAuth":q?"Cookie":(e?.provider?.includes("freebuff")||"openai-compatible-chat-freebuff"===e?.provider)?"Session Token":"API Key"'
        c = c.replace(old_badge, new_badge)

        old_acc_name = '(_?"OAuth Account":q?"Cookie Account":"API Key")'
        new_acc_name = '(_?"OAuth Account":q?"Cookie Account":(e?.provider?.includes("freebuff")||"openai-compatible-chat-freebuff"===e?.provider)?"Session Account":"API Key")'
        c = c.replace(old_acc_name, new_acc_name)

        old_icon = 'children:q?"cookie":_?"lock":"key"'
        new_icon = 'children:q?"cookie":_?"lock":(e?.provider?.includes("freebuff")||"openai-compatible-chat-freebuff"===e?.provider)?"token":"key"'
        c = c.replace(old_icon, new_icon)

        # 4.14 Guidance card
        c = inject_guidance_card(c, is_server=False)

        with open(p, "w", encoding="utf-8") as f:
            f.write(c)
        print(f"  [+] Patched client provider detail page: {os.path.basename(p)}")

    # 5. Detail Page: /dashboard/providers/[id] (Server page.js)
    p_s_detail = os.path.join(build_dir, "server/app/(dashboard)/dashboard/providers/[id]/page.js")
    if os.path.exists(p_s_detail):
        with open(p_s_detail, "r", encoding="utf-8") as f:
            cs = f.read()

        # 5.1 Detail page header logo
        if 'bh.id?.includes("freebuff")' not in cs:
            cs = cs.replace('b5=()=>bp&&bh.apiType?', 'b5=()=>bh.id?.includes("freebuff")?"/providers/freebuff.png":bp&&bh.apiType?')

        # 5.2 Variable reordering so br is defined before bn
        broken_order = 'bm=(0,m.KC)(q),bn=("cursor"===q||"zed"===q)&&aM.length>0?aM:bm,bo=(0,l.wG)(q),bp=(0,l.mq)(q),bq=(0,l.gb)(q),br=bp||bq'
        fixed_order = 'bo=(0,l.wG)(q),bp=(0,l.mq)(q),bq=(0,l.gb)(q),br=bp||bq,bm=(0,m.KC)(q),bn=("cursor"===q||"zed"===q||br)&&aM.length>0?aM:bm'
        cs = cs.replace(broken_order, fixed_order)

        # 5.3 Bypass compatible form E
        cs = cs.replace('if(br)return(0,d.jsx)(E,', 'if(false)return(0,d.jsx)(E,')
        # 5.4 Enable tag list
        cs = cs.replace('!br&&(a=[...bn,', 'true&&(a=[...bn,')
        # 5.5 Enable add modal
        cs = cs.replace('!br&&(0,d.jsx)(M,{isOpen:au,providerAlias:bw', 'true&&(0,d.jsx)(M,{isOpen:au,providerAlias:bw')

        # 5.6 Header Add button & Connection Add button
        cs = cs.replace('children:br?"Add API Key":"iflow"===q?"OAuth":"Add Connection"', 'children:(br&&!q.includes("freebuff"))?"Add API Key":"Add"')
        cs = cs.replace('br?"Add API Key":', 'br?"Add":')

        # 5.7 Field label
        old_s_lbl = 'bu="xai"===q?"xAI API Key":"kimi"===q?"Kimi API Key":"qoder"===q||"qoder-cn"===q?"PAT":"API Key"'
        new_s_lbl = 'bu=q?.includes("freebuff")?"FreeBuff CLI Token":"xai"===q?"xAI API Key":"kimi"===q?"Kimi API Key":"qoder"===q||"qoder-cn"===q?"PAT":"API Key"'
        cs = cs.replace(old_s_lbl, new_s_lbl)

        # 5.8 Name placeholder
        old_s_name_ph = 'placeholder:t?"Ollama Local":"Production Key"'
        new_s_name_ph = 'placeholder:b?.includes("freebuff")?"FreeBuff Account":t?"Ollama Local":"Production Key"'
        cs = cs.replace(old_s_name_ph, new_s_name_ph)

        # 5.9 Input placeholder
        old_s_inp_ph = ':"qoder"===b||"qoder-cn"===b?"pt-...":""'
        new_s_inp_ph = ':"qoder"===b||"qoder-cn"===b?"pt-...":b?.includes("freebuff")?"Paste FreeBuff token...":""'
        cs = cs.replace(old_s_inp_ph, new_s_inp_ph)

        # 5.10 Test button
        old_s_btn = 'children:L?"Checking...":"Check"'
        new_s_btn = 'children:L?"Testing...":(b?.includes("freebuff")?"Test Connection":"Check")'
        cs = cs.replace(old_s_btn, new_s_btn)

        # 5.11 Hide Default Model field for FreeBuff
        old_s_dm = 'f&&(0,d.jsx)(k.pd,{label:"Default Model"'
        new_s_dm = 'f&&!b?.includes("freebuff")&&(0,d.jsx)(k.pd,{label:"Default Model"'
        cs = cs.replace(old_s_dm, new_s_dm)

        # 5.12 Guidance card
        cs = inject_guidance_card(cs, is_server=True)

        with open(p_s_detail, "w", encoding="utf-8") as f:
            f.write(cs)
        print("  [+] Patched server provider detail page: page.js")

    # 6. Edit modal hint in 412.js & 5497-*.js
    p_412 = os.path.join(build_dir, "server/chunks/412.js")
    if os.path.exists(p_412):
        with open(p_412, "r", encoding="utf-8") as f:
            c412 = f.read()
        if 'freebuff' not in c412:
            c412 = c412.replace('b?.provider?.includes("chatgpt")', 'b?.provider?.includes("freebuff")||b?.provider?.includes("chatgpt")')
            with open(p_412, "w", encoding="utf-8") as f:
                f.write(c412)
            print("  [+] Patched server edit modal hint in 412.js")

    for p in glob.glob(os.path.join(build_dir, "static/chunks/5497-*.js")):
        with open(p, "r", encoding="utf-8") as f:
            c5497 = f.read()
        if 'freebuff' not in c5497:
            c5497 = c5497.replace('t?.provider?.includes("chatgpt")', 't?.provider?.includes("freebuff")||t?.provider?.includes("chatgpt")')
            with open(p, "w", encoding="utf-8") as f:
                f.write(c5497)
            print(f"  [+] Patched client edit modal hint in {os.path.basename(p)}")

    print("\n[✓] 9Router High-Grade UX Patcher executed successfully.")

if __name__ == "__main__":
    run()
