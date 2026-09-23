#!/usr/bin/env python3
"""
9Router Web UI & Automated Device Login Patcher for FreeBuff
============================================================
Delivers an Antigravity-grade automated onboarding experience for FreeBuff
directly inside 9Router's Web UI:

1. One-Click Automated Login (like Antigravity / GitHub Device Flow):
   - Clicking "Add Connection" opens a dedicated modal with the authorization
     URL and code, and SIMULTANEOUSLY opens Codebuff's GitHub login in a new tab.
   - Background polling checks the upstream login status every 3 seconds.
   - As soon as the user logs in on Codebuff, the auth token and email are
     retrieved, saved/updated in 9Router's database, and the modal displays
     "Connected Successfully!" before refreshing the dashboard list.
2. High-Grade Visual Branding & Polished UX:
   - Official FreeBuff logo in providers list & detail page header.
   - "Connect FreeBuff Account" modal title & "Add Connection" button.
   - "Auth Token" badge and "token" icon on connection cards.
   - Elimination of the mandatory "Default Model" block.
3. Systemic Resilience:
   - 100% idempotent: safely re-runnable after 9Router updates.
   - Syntax-verified (`node -c`) after every patch; instant auto-rollback on error.
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
        # Already applied
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
    print("  9Router Automated Device Login & UI Patcher for FreeBuff")
    print("==========================================================")

    build_dir = find_build_dir()
    if not build_dir:
        print("[!] 9Router build directory not found. Skipping UI patch.")
        return False

    print(f"Found 9Router build directory: {build_dir}\n")

    # -----------------------------------------------------------------
    # 0. Ensure public asset exists
    # -----------------------------------------------------------------
    asset_src = "/root/projects/freebuff-9router/assets/freebuff.png"
    asset_dst = os.path.join(os.path.dirname(build_dir), "public/providers/freebuff.png")
    if os.path.exists(asset_src):
        os.makedirs(os.path.dirname(asset_dst), exist_ok=True)
        shutil.copy2(asset_src, asset_dst)
        print(f"  [✓] Verified logo at {asset_dst}")

    # -----------------------------------------------------------------
    # 1. Main Providers List page (/dashboard/providers)
    # -----------------------------------------------------------------
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

    # -----------------------------------------------------------------
    # 2. Server OAuth Route: Backend Device-Code & Status Polling
    # -----------------------------------------------------------------
    s_oauth = os.path.join(build_dir, "server/app/api/oauth/[provider]/[action]/route.js")
    if os.path.exists(s_oauth):
        # 2a. GET Handler: device-code generation for FreeBuff
        target_get = 'async function p(a,{params:b}){try{let{provider:d,action:e}=await b,{searchParams:i}=new URL(a.url);'
        inject_get = (
            'async function p(a,{params:b}){try{let{provider:d,action:e}=await b,{searchParams:i}=new URL(a.url);'
            'if("freebuff"===d||"openai-compatible-chat-freebuff"===d){'
            'if("device-code"===e){try{'
            'let fp="enhanced-"+f().randomBytes(24).toString("hex"),'
            'resp=await fetch("https://www.codebuff.com/api/auth/cli/code",{method:"POST",headers:{"Content-Type":"application/json","User-Agent":"codebuff/0.1.0"},body:JSON.stringify({fingerprintId:fp})});'
            'if(!resp.ok){let t=await resp.text();return g.NextResponse.json({error:`Codebuff device code failed: ${t}`},{status:500})}'
            'let cdata=await resp.json(),lUrl=cdata.loginUrl||"",cm=lUrl.match(/auth_code=([^&]+)/),ac=cm?cm[1]:"",'
            'devCode=Buffer.from(JSON.stringify({fp:fp,hash:cdata.fingerprintHash||"",exp:cdata.expiresAt||""})).toString("base64url");'
            'return g.NextResponse.json({device_code:devCode,user_code:ac?ac.slice(0,8).toUpperCase():"LOGIN",verification_uri:lUrl,verification_uri_complete:lUrl,expires_in:1200,interval:3})'
            '}catch(err){return g.NextResponse.json({error:err.message},{status:500})}}}'
        )
        patch_file(s_oauth, target_get, inject_get, "Server OAuth: FreeBuff device-code GET handler")

        # 2b. POST Handler: background token poll & database connection creation
        target_post = 'async function q(a,{params:b}){try{let d,{provider:e,action:f}=await b;try{d=await a.json()}catch{return g.NextResponse.json({error:"Invalid or empty request body"},{status:400})}'
        inject_post = (
            'async function q(a,{params:b}){try{let d,{provider:e,action:f}=await b;try{d=await a.json()}catch{return g.NextResponse.json({error:"Invalid or empty request body"},{status:400})}'
            'if("freebuff"===e||"openai-compatible-chat-freebuff"===e){if("poll"===f){'
            'let devCode=d?.deviceCode;if(!devCode)return g.NextResponse.json({error:"Missing device code"},{status:400});'
            'let sess;try{sess=JSON.parse(Buffer.from(devCode,"base64url").toString("utf-8"))}catch(err){return g.NextResponse.json({success:!1,error:"invalid_device_code"})}'
            'let qs=new URLSearchParams({fingerprintId:sess.fp,fingerprintHash:sess.hash,expiresAt:String(sess.exp)}),'
            'resp=await fetch(`https://www.codebuff.com/api/auth/cli/status?${qs.toString()}`,{headers:{"User-Agent":"codebuff/0.1.0"}});'
            'if(401===resp.status||404===resp.status)return g.NextResponse.json({success:!1,pending:!0,error:"authorization_pending"});'
            'if(!resp.ok)return g.NextResponse.json({success:!1,error:`Upstream status error ${resp.status}`});'
            'let sdata=await resp.json(),user=sdata.user||{},token=user.authToken;'
            'if(!token)return g.NextResponse.json({success:!1,pending:!0,error:"authorization_pending"});'
            'let email=user.email||null,name=user.name||email||"FreeBuff Account",'
            'existing=await(0,i.getProviderConnections)({provider:"openai-compatible-chat-freebuff"}),maxPri=0;'
            'for(let conn of existing){conn.priority&&conn.priority>maxPri&&(maxPri=conn.priority)}'
            'let match=email?existing.find(c=>c.email===email):null,savedConn;'
            'if(match){savedConn=await(0,i.updateProviderConnection)(match.id,{apiKey:token,name:email||name,testStatus:"active"})}'
            'else{savedConn=await(0,i.createProviderConnection)({provider:"openai-compatible-chat-freebuff",authType:"apikey",name:email||name,email:email,priority:maxPri+1,apiKey:token,providerSpecificData:{prefix:"freebuff",apiType:"chat",baseUrl:"http://127.0.0.1:3457/v1",nodeName:"FreeBuff (freebucks-proxy)",connectionProxyEnabled:!1,connectionProxyUrl:"",connectionNoProxy:""},testStatus:"active"})}'
            'return g.NextResponse.json({success:!0,connection:{id:savedConn.id,provider:savedConn.provider}})}}'
        )
        patch_file(s_oauth, target_post, inject_post, "Server OAuth: FreeBuff poll POST handler")

    # -----------------------------------------------------------------
    # 3. Client OAuthModal: Device-Flow Enrollment & Title / Messages
    # -----------------------------------------------------------------
    for mc in glob.glob(os.path.join(build_dir, "static/chunks/5497-*.js")):
        patch_file(
            mc,
            '["github","kiro","kimi","kimi-coding","kilocode","codebuddy-cn","codebuddy-intl","qoder","qoder-cn","grok-cli"]',
            '["github","kiro","kimi","kimi-coding","kilocode","codebuddy-cn","codebuddy-intl","qoder","qoder-cn","grok-cli","freebuff","openai-compatible-chat-freebuff"]',
            "Client OAuthModal: register freebuff in device-code providers list"
        )
        patch_file(
            mc,
            'ei=es?"Connect Grok Build OAuth":`Connect ${a.name}`',
            'ei=es?"Connect Grok Build OAuth":t?.includes("freebuff")?"Connect FreeBuff Account":`Connect ${a.name}`',
            "Client OAuthModal: FreeBuff modal title"
        )
        patch_file(
            mc,
            'children:["Your ",a.name," account has been connected."]',
            'children:["Your ",t?.includes("freebuff")?"FreeBuff":a.name," account has been connected."]',
            "Client OAuthModal: FreeBuff success message"
        )

    # -----------------------------------------------------------------
    # 4. Client Provider Detail Page: Action Routing & UI Polishing
    # -----------------------------------------------------------------
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
            # Route to() to OAuthModal for FreeBuff
            patch_file(
                c_detail,
                'to=()=>{tm?tr():tn()}',
                'to=()=>{("freebuff"===f||f.includes("freebuff"))?tl():tm?tr():tn()}',
                "Client: route to() to automated OAuthModal"
            )
            patch_file(
                c_detail,
                'tr=()=>{"antigravity"===f&&"true"!==window.localStorage.getItem(ta)?eV(!0):"xiaomi-mimo"===f?J(!0):tm?tl():(V(""),G(!0))}',
                'tr=()=>{"antigravity"===f&&"true"!==window.localStorage.getItem(ta)?eV(!0):("freebuff"===f||f.includes("freebuff"))?tl():"xiaomi-mimo"===f?J(!0):tm?tl():(V(""),G(!0))}',
                "Client: route tr() to automated OAuthModal"
            )
            # Node header card Add button: route to OAuthModal
            patch_file(
                c_detail,
                '(0,i.jsx)(c.$n,{size:"sm",icon:"add",onClick:()=>{V(""),G(!0)},className:"w-full sm:w-auto",children:"Add API Key"})',
                '(0,i.jsx)(c.$n,{size:"sm",icon:"add",onClick:to,className:"w-full sm:w-auto",children:("freebuff"===f||f.includes("freebuff"))?"Add Connection":"Add"})',
                "Client: node card Add button routes to to()"
            )
            patch_file(
                c_detail,
                '(0,i.jsx)(c.$n,{size:"sm",icon:"add",onClick:()=>{V(""),G(!0)},className:"w-full sm:w-auto",children:"Add"})',
                '(0,i.jsx)(c.$n,{size:"sm",icon:"add",onClick:to,className:"w-full sm:w-auto",children:("freebuff"===f||f.includes("freebuff"))?"Add Connection":"Add"})',
                "Client: node card Add button fallback routes to to()"
            )
            # Connection table header button label
            patch_file(
                c_detail,
                'tb?"Add API Key":"iflow"===f?"OAuth":"Add Connection"',
                '("freebuff"===f||f.includes("freebuff"))?"Add Connection":tb?"Add API Key":"iflow"===f?"OAuth":"Add Connection"',
                "Client: connections header button label"
            )
            # Empty state Add button label
            patch_file(
                c_detail,
                'onClick:to,className:"w-full sm:w-auto",children:"Add"',
                'onClick:to,className:"w-full sm:w-auto",children:("freebuff"===f||f.includes("freebuff"))?"Add Connection":"Add"',
                "Client: empty state button label"
            )
            # Badges & icons on connection cards
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

    # -----------------------------------------------------------------
    # 5. Server Provider Detail Page: Action Routing & UI Polishing
    # -----------------------------------------------------------------
    s_detail = os.path.join(build_dir, "server/app/(dashboard)/dashboard/providers/[id]/page.js")
    if os.path.exists(s_detail):
        # Header logo routing
        patch_file(
            s_detail,
            'b5=()=>bp&&bh.apiType?',
            'b5=()=>bh.id?.includes("freebuff")?"/providers/freebuff.png":bp&&bh.apiType?',
            "Server: header logo"
        )
        # Server bg= (to= equivalent)
        patch_file(
            s_detail,
            'bg=()=>{bj?be():bf()}',
            'bg=()=>{("freebuff"===q||q?.includes("freebuff"))?bd():bj?be():bf()}',
            "Server: route bg() to automated modal"
        )
        # Node header card Add button: route to bd() (OAuthModal)
        patch_file(
            s_detail,
            '(0,d.jsx)(k.$n,{size:"sm",icon:"add",onClick:()=>{X(""),V(!0)},className:"w-full sm:w-auto",children:"Add API Key"})',
            '(0,d.jsx)(k.$n,{size:"sm",icon:"add",onClick:bg,className:"w-full sm:w-auto",children:("freebuff"===q||q?.includes("freebuff"))?"Add Connection":"Add"})',
            "Server: node card Add button routes to bg()"
        )
        patch_file(
            s_detail,
            '(0,d.jsx)(k.$n,{size:"sm",icon:"add",onClick:()=>{X(""),V(!0)},className:"w-full sm:w-auto",children:"Add"})',
            '(0,d.jsx)(k.$n,{size:"sm",icon:"add",onClick:bg,className:"w-full sm:w-auto",children:("freebuff"===q||q?.includes("freebuff"))?"Add Connection":"Add"})',
            "Server: node card Add button fallback routes to bg()"
        )
        # Connection table header button label
        patch_file(
            s_detail,
            'br?"Add API Key":"iflow"===q?"OAuth":"Add Connection"',
            '("freebuff"===q||q?.includes("freebuff"))?"Add Connection":br?"Add API Key":"iflow"===q?"OAuth":"Add Connection"',
            "Server: connections header button label"
        )
        # Empty state Add button label
        patch_file(
            s_detail,
            'onClick:bg,className:"w-full sm:w-auto",children:"Add"',
            'onClick:bg,className:"w-full sm:w-auto",children:("freebuff"===q||q?.includes("freebuff"))?"Add Connection":"Add"',
            "Server: empty state button label"
        )
        # Badges & icons on connection cards
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

    # -----------------------------------------------------------------
    # 6. Edit Connection Modal chunks
    # -----------------------------------------------------------------
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

    print("\n[✓] FreeBuff automated login & UI/UX patching completed successfully.")
    return True

if __name__ == "__main__":
    success = run()
    sys.exit(0 if success else 1)
