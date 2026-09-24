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

    matched_old = None
    if isinstance(old_str, list):
        for candidate in old_str:
            if candidate in content:
                matched_old = candidate
                break
    elif old_str in content:
        matched_old = old_str

    if not matched_old:
        print(f"  [?] Target not found for {label} in {os.path.basename(filepath)}")
        return False

    backup_path = filepath + ".bak"
    shutil.copy2(filepath, backup_path)

    new_content = content.replace(matched_old, new_str, 1)
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
    script_dir = os.path.dirname(os.path.abspath(__file__))
    asset_src = os.path.join(script_dir, "assets/freebuff.png")
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
            'else{savedConn=await(0,i.createProviderConnection)({provider:"openai-compatible-chat-freebuff",authType:"apikey",name:email||name,email:email,priority:maxPri+1,apiKey:token,providerSpecificData:{prefix:"freebuff",apiType:"chat",baseUrl:"http://127.0.0.1:3457/v1",nodeName:"FreeBuff",connectionProxyEnabled:!1,connectionProxyUrl:"",connectionNoProxy:""},testStatus:"active"})}'
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
    models_json = '[{"id":"deepseek/deepseek-v4-flash","name":"DeepSeek V4 Flash","contextLength":1048576,"capabilities":["reasoning"]},{"id":"z-ai/glm-5.3-flash","name":"GLM 5.3 Flash (Vision)","contextLength":200000,"capabilities":["vision"]},{"id":"upstage/solar-pro4","name":"Solar Pro 4","contextLength":128000},{"id":"mimo/mimo-v2.5","name":"MiMo V2.5","contextLength":1048576},{"id":"mimo/mimo-v2.6-pro","name":"MiMo V2.6 Pro","contextLength":1048576,"capabilities":["reasoning"]},{"id":"openai/gpt-5.6-luna","name":"GPT 5.6 Luna","contextLength":1048576},{"id":"google/gemini-3.8-flash","name":"Gemini 3.8 Flash","contextLength":1048576,"capabilities":["vision"]},{"id":"anthropic/claude-fable-5.1","name":"Claude Fable 5.1","contextLength":200000,"capabilities":["vision","reasoning"]},{"id":"meta/muse-spark-1.2-contributor","name":"Muse Spark 1.2 Contributor","contextLength":128000}]'

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

            # Antigravity-grade Available Models UI for FreeBuff
            patch_file(
                c_detail,
                'tx=(0,p.KC)(f),th=("cursor"===f||"zed"===f)&&eU.length>0?eU:tx,',
                f'tx=(0,p.KC)(f),th=f.includes("freebuff")?{models_json}:("cursor"===f||"zed"===f)&&eU.length>0?eU:tx,',
                "Client: FreeBuff model catalog in th"
            )
            patch_file(
                c_detail,
                ',!tb&&(e=[...th,...eF.filter(e=>!th.some(t=>t.id===e.id))].filter(e=>{let t=(0,p.CP)(e);return!t||"llm"===t}).map(e=>e.id).filter(e=>!eW.includes(e)),(0,i.jsxs)("div",{className:"flex gap-2",children:[eW.length>0&&(0,i.jsx)(c.$n,{size:"sm",variant:"secondary",icon:"restart_alt",onClick:tP,children:"Active All"}),e.length>0&&(0,i.jsx)(c.$n,{size:"sm",variant:"secondary",icon:"block",onClick:()=>tO(e),children:"Disable All"})]}))]})',
                ',(!tb||f.includes("freebuff"))&&(e=[...th,...eF.filter(e=>!th.some(t=>t.id===e.id))].filter(e=>{let t=(0,p.CP)(e);return!t||"llm"===t}).map(e=>e.id).filter(e=>!eW.includes(e)),(0,i.jsxs)("div",{className:"flex gap-2",children:[eW.length>0&&(0,i.jsx)(c.$n,{size:"sm",variant:"secondary",icon:"restart_alt",onClick:tP,children:"Active All"}),e.length>0&&(0,i.jsx)(c.$n,{size:"sm",variant:"secondary",icon:"block",onClick:()=>tO(e),children:"Disable All"})]}))]})',
                "Client: FreeBuff Active All and Disable All buttons"
            )
            patch_file(
                c_detail,
                'if(tb)return(0,i.jsx)(E,{providerStorageAlias:tN,providerDisplayAlias:tS,modelAliases:ed,customModels:em,copied:ts,onCopy:ti,onSetAlias:tU,onDeleteAlias:tK,onAddCustomModel:e=>tJ(e,"llm",tN),onDeleteCustomModel:e=>tM(e,"llm",tN),connections:y,isAnthropic:ty});',
                'if(tb&&!f.includes("freebuff"))return(0,i.jsx)(E,{providerStorageAlias:tN,providerDisplayAlias:tS,modelAliases:ed,customModels:em,copied:ts,onCopy:ti,onSetAlias:tU,onDeleteAlias:tK,onAddCustomModel:e=>tJ(e,"llm",tN),onDeleteCustomModel:e=>tM(e,"llm",tN),connections:y,isAnthropic:ty});',
                "Client: FreeBuff skip generic OpenAI table and render Antigravity cards & disabled pills"
            )
            patch_file(
                c_detail,
                '!tb&&(0,i.jsx)(K,{isOpen:ej,providerAlias:tN,providerDisplayAlias:tS,onSave:async(e,t)=>{await tJ(e,"llm",tN,t),ew(!1)},onClose:()=>ew(!1)})',
                '(!tb||f.includes("freebuff"))&&(0,i.jsx)(K,{isOpen:ej,providerAlias:tN,providerDisplayAlias:tS,onSave:async(e,t)=>{await tJ(e,"llm",tN,t),ew(!1)},onClose:()=>ew(!1)})',
                "Client: FreeBuff Add Model modal"
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

        # Antigravity-grade Available Models UI for FreeBuff (Server)
        patch_file(
            s_detail,
            'bm=(0,m.KC)(q),bn=("cursor"===q||"zed"===q)&&aM.length>0?aM:bm,',
            f'bm=(0,m.KC)(q),bn=q.includes("freebuff")?{models_json}:("cursor"===q||"zed"===q)&&aM.length>0?aM:bm,',
            "Server: FreeBuff model catalog in bn"
        )
        patch_file(
            s_detail,
            ',!br&&(a=[...bn,...aQ.filter(a=>!bn.some(b=>b.id===a.id))].filter(a=>{let b=(0,m.CP)(a);return!b||"llm"===b}).map(a=>a.id).filter(a=>!aS.includes(a)),(0,d.jsxs)("div",{className:"flex gap-2",children:[aS.length>0&&(0,d.jsx)(k.$n,{size:"sm",variant:"secondary",icon:"restart_alt",onClick:bD,children:"Active All"}),a.length>0&&(0,d.jsx)(k.$n,{size:"sm",variant:"secondary",icon:"block",onClick:()=>bC(a),children:"Disable All"})]}))]})',
            ',(!br||q.includes("freebuff"))&&(a=[...bn,...aQ.filter(a=>!bn.some(b=>b.id===a.id))].filter(a=>{let b=(0,m.CP)(a);return!b||"llm"===b}).map(a=>a.id).filter(a=>!aS.includes(a)),(0,d.jsxs)("div",{className:"flex gap-2",children:[aS.length>0&&(0,d.jsx)(k.$n,{size:"sm",variant:"secondary",icon:"restart_alt",onClick:bD,children:"Active All"}),a.length>0&&(0,d.jsx)(k.$n,{size:"sm",variant:"secondary",icon:"block",onClick:()=>bC(a),children:"Disable All"})]}))]})',
            "Server: FreeBuff Active All and Disable All buttons"
        )
        patch_file(
            s_detail,
            'if(br)return(0,d.jsx)(E,{providerStorageAlias:bw,providerDisplayAlias:by,modelAliases:ai,customModels:ak,copied:bb,onCopy:bc,onSetAlias:bL,onDeleteAlias:bM,onAddCustomModel:a=>bN(a,"llm",bw),onDeleteCustomModel:a=>bO(a,"llm",bw),connections:s,isAnthropic:bq});',
            'if(br&&!q.includes("freebuff"))return(0,d.jsx)(E,{providerStorageAlias:bw,providerDisplayAlias:by,modelAliases:ai,customModels:ak,copied:bb,onCopy:bc,onSetAlias:bL,onDeleteAlias:bM,onAddCustomModel:a=>bN(a,"llm",bw),onDeleteCustomModel:a=>bO(a,"llm",bw),connections:s,isAnthropic:bq});',
            "Server: FreeBuff skip generic OpenAI table and render Antigravity cards & disabled pills"
        )
        patch_file(
            s_detail,
            '!br&&(0,d.jsx)(M,{isOpen:au,providerAlias:bw,providerDisplayAlias:by,onSave:async(a,b)=>{await bN(a,"llm",bw,b),av(!1)},onClose:()=>av(!1)})',
            '(!br||q.includes("freebuff"))&&(0,d.jsx)(M,{isOpen:au,providerAlias:bw,providerDisplayAlias:by,onSave:async(a,b)=>{await bN(a,"llm",bw,b),av(!1)},onClose:()=>av(!1)})',
            "Server: FreeBuff Add Model modal"
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

    # -----------------------------------------------------------------
    # 7. Server Model Router: Short-Name Aliasing for FreeBuff
    # -----------------------------------------------------------------
    target_router = 'let a=(await (0,d.Fh)({type:"openai-compatible"})).find(a=>a.prefix===c.providerAlias);if(a)return{provider:a.id,model:c.model};'
    repl_router = (
        'let a=(await (0,d.Fh)({type:"openai-compatible"})).find(a=>a.prefix===c.providerAlias);'
        'if(a){let m=c.model;if(c.providerAlias==="freebuff"||a.id.includes("freebuff")){'
        'let fbMap={"deepseek-v4-flash":"deepseek/deepseek-v4-flash","glm-5.3-flash":"z-ai/glm-5.3-flash","solar-pro":"upstage/solar-pro4","solar-pro4":"upstage/solar-pro4","mimo-v2.6-pro":"mimo/mimo-v2.6-pro","mimo-v2.5":"mimo/mimo-v2.5","gpt-5.6-luna":"openai/gpt-5.6-luna","gemini-3.8-flash":"google/gemini-3.8-flash","claude-fable-5.1":"anthropic/claude-fable-5.1","muse-spark-1.2-contributor":"meta/muse-spark-1.2-contributor"};'
        'm=fbMap[m]||m}return{provider:a.id,model:m};}'
    )
    for c_chunk in [os.path.join(build_dir, "server/chunks/8635.js"), os.path.join(build_dir, "server/chunks/9128.js")]:
        if os.path.exists(c_chunk):
            patch_file(c_chunk, target_router, repl_router, f"Server router: FreeBuff model alias mapping ({os.path.basename(c_chunk)})")

    # -----------------------------------------------------------------
    # 8. Server FreeBuff Sequential & Exhaust-First Session Guardian
    # -----------------------------------------------------------------
    # 8a. Hard-lock FreeBuff connection routing to fill-first (sequential only, immune to round-robin)
    c_4572 = os.path.join(build_dir, "server/chunks/4572.js")
    if os.path.exists(c_4572):
        target_strategy = 'let r=await (0,d.mt)(),s=(r.providerStrategies||{})[g]||{},t=s.fallbackStrategy||r.fallbackStrategy||"fill-first";'
        repl_strategy = 'let r=await (0,d.mt)(),s=(r.providerStrategies||{})[g]||{},t=(g?.includes("freebuff")||a?.includes("freebuff"))?"fill-first":(s.fallbackStrategy||r.fallbackStrategy||"fill-first");'
        patch_file(c_4572, target_strategy, repl_strategy, "Server connection selector: FreeBuff fill-first enforcement (4572.js)")

        target_clamp = 'k&&k>Date.now()?(l=!0,n="antigravity"===(0,h.rs)(e)?k-Date.now():Math.min(k-Date.now(),g.fh),o=0)'
        repl_clamp = 'k&&k>Date.now()?(l=!0,n=("antigravity"===(0,h.rs)(e)||e?.includes("freebuff"))?k-Date.now():Math.min(k-Date.now(),g.fh),o=0)'
        patch_file(c_4572, target_clamp, repl_clamp, "Server connection selector: FreeBuff unclamp cooldown (4572.js)")

    # 8b. FreeBuff Exhaust-First Fallback Guardian:
    #     Transient errors (500/502/503/504 or short 429) keep the current account pinned to prevent multi-session bleeding.
    #     Only genuine daily exhaustion (401/402/403 or quota limit/reset 429) triggers failover with lockout.
    c_8635 = os.path.join(build_dir, "server/chunks/8635.js")
    if os.path.exists(c_8635):
        with open(c_8635, "r", encoding="utf-8") as f:
            c_8635_content = f.read()

        # Inject _disMod=c(9248) at top of module 79489 so we can call _disMod.vF() inside z()
        target_disMod = 'var e=c(48895),'
        repl_disMod = 'var _disMod=c(9248),e=c(48895),'
        if '_disMod' not in c_8635_content and target_disMod in c_8635_content:
            patch_file(c_8635, target_disMod, repl_disMod, "Server router: inject _disMod=c(9248) for disabled model check (8635.js)")
            # Re-read after patch
            with open(c_8635, "r", encoding="utf-8") as f:
                c_8635_content = f.read()

        # Check disabled models at router entry — uses _disMod.vF() with flexible suffix matching
        target_dis_check = 'let{provider:w,model:x}=q,y=d?.headers?.get("user-agent")||"",A=new Set,B=null,C=null;'
        repl_dis_check = (
            'let{provider:w,model:x}=q;'
            'try{let _dis=await _disMod.vF();let _dl=_dis[w]||_dis["openai-compatible-chat-freebuff"]||_dis["freebuff"]||[];'
            'let _cleanM=b.includes("/")?b.slice(b.indexOf("/")+1):b;'
            'let _isDis=Array.isArray(_dl)&&_dl.some(d=>d===x||d===b||d===_cleanM||d.split("/").pop()===_cleanM.split("/").pop()||d.split("/").pop()===x.split("/").pop());'
            'if(_isDis){'
            'return t.warn("CHAT",`Model \'${b}\' is disabled`),(0,n.yj)(r.gx.BAD_REQUEST,`Model \'${b}\' is disabled`);}}catch(e){}'
            'let y=d?.headers?.get("user-agent")||"",A=new Set,B=null,C=null;'
        )
        if "Model '${b}' is disabled" not in c_8635_content and target_dis_check in c_8635_content:
            patch_file(c_8635, target_dis_check, repl_dis_check, "Server router: FreeBuff disabled model interceptor (8635.js)")

        target_fb_fallback = 'if("antigravity"===w&&(409===q.status||429===q.status)&&(z=await (0,g.XJ)(b.connectionId,q.status,x,i.accessToken,b.providerSpecificData))&&(D=z),"antigravity"===w&&z||(await (0,f.vk)(b.connectionId,q.status,q.error,w,x,D)).shouldFallback){t.warn("FALLBACK",`⇄ ACC:${b.connectionName} UNAVAILABLE (${q.status}) → NEXT ACCOUNT`),A.add(b.connectionId),B=q.error,C=q.status;continue}'

        repl_fb_guardian = (
            'let isFb=w?.includes("freebuff");'
            'if(isFb){'
            'let fbCode=Number(q.status);'
            'if(fbCode>=400&&fbCode<500&&fbCode!==401&&fbCode!==402&&fbCode!==403&&fbCode!==429){'
            'return q.response;}'
            'if(fbCode===429||fbCode>=500||fbCode===401||fbCode===402||fbCode===403){'
            'let fbText=(typeof q.error==="object"?JSON.stringify(q.error):String(q.error||"")).toLowerCase();'
            'let isAuthFailure=fbCode===401||(fbCode===502&&(fbText.includes("upstream_auth_rejected")||fbText.includes("auth rejected")||fbText.includes("invalid token")||fbText.includes("token revoked")||fbText.includes("unauthorized")));'
            'let isAccountBan=fbCode===403&&(fbText.includes("banned")||fbText.includes("suspended")||fbText.includes("account_banned")||fbText.includes("account_suspended"));'
            'let isExplicitTransient=(fbText.includes("turn_spend_limit")||fbText.includes("turn_spend_limited")||fbText.includes("turn spend limit")||fbText.includes("load_shedding")||fbText.includes("limit_burst_rate")||fbText.includes("peak_hours")||fbText.includes("peak hours")||fbText.includes("free_mode_run_fanout")||fbText.includes("free_mode_capacity_deferred")||fbText.includes("waiting_room_queued")||fbText.includes("waiting_room_required")||fbText.includes("session_superseded")||fbText.includes("ip_capped"));'
            'let resetMatch=fbText.match(/resets?\\s+at\\s+([0-9a-z:\\.\\-]+)/i);'
            'let parsedResetMs=null;'
            'if(resetMatch){let dt=new Date(resetMatch[1].toUpperCase()).getTime();if(!isNaN(dt)&&dt>Date.now())parsedResetMs=dt;}'
            'let retryMatch=fbText.match(/retry\\s+after\\s+([0-9]+)\\s*([smhd]?)/i);'
            'let parsedRetryMs=null;'
            'if(retryMatch){let num=parseInt(retryMatch[1],10);let unit=retryMatch[2]?.toLowerCase();let mult=unit==="h"?3600000:unit==="m"?60000:unit==="d"?86400000:1000;if(!isNaN(num))parsedRetryMs=Date.now()+(num*mult);}'
            'let isLongRetry=(parsedRetryMs&&parsedRetryMs>Date.now()+600000)||(D&&D>Date.now()+600000);'
            'let hasQuotaKeywords=(fbText.includes("allowance")||fbText.includes("ceiling")||fbText.includes("exhaust")||fbText.includes("spent")||fbText.includes("freebucks")||fbText.includes("shortfall")||fbText.includes("daily quota")||fbText.includes("payment_required")||fbText.includes("payment required")||(fbText.includes("insufficient_quota")&&(parsedResetMs||isLongRetry)));'
            'let isExhausted=false;'
            'if(isAuthFailure||isAccountBan||fbCode===402){isExhausted=true;}'
            'else if(fbCode===429&&!isExplicitTransient){if(parsedResetMs!==null||isLongRetry||hasQuotaKeywords){isExhausted=true;}}'
            'if(!isExhausted){'
            't.warn("FREEBUFF_GUARDIAN",`[FreeBuff Guardian] Transient error (${fbCode}) on ${b.connectionName} - keeping account pinned to prevent multi-session bleeding`);'
            'return q.response;}'
            'let lockMs=parsedResetMs||parsedRetryMs||(D&&D>Date.now()?D:Date.now()+43200000);'
            'await (0,f.vk)(b.connectionId,fbCode,q.error,w,null,lockMs);'
            'let resetStr=new Date(lockMs).toISOString();'
            't.warn("FALLBACK",`[FreeBuff Guardian] Account ${b.connectionName} quota/auth exhausted (${fbCode}, reset: ${resetStr}) → sequentially promoting next account`);'
            'A.add(b.connectionId),B=q.error,C=fbCode;continue;}'
            'if(fbCode<500&&fbCode!==429&&fbCode!==401&&fbCode!==402&&fbCode!==403){'
            'return q.response;}}'
        )

        # Match existing guardian snippets in 8635.js if present
        current_snippet = None
        if os.path.exists(c_8635):
            with open(c_8635, "r", encoding="utf-8") as f:
                content = f.read()
            idx = content.find("FREEBUFF_GUARDIAN")
            if idx != -1:
                start = content.rfind('let isFb=w?.includes("freebuff");', 0, idx)
                end = content.find('if("antigravity"===w', idx)
                if start != -1 and end != -1:
                    current_snippet = content[start:end]

        candidates = [c for c in [current_snippet, target_fb_fallback] if c]
        patch_file(c_8635, candidates, repl_fb_guardian + target_fb_fallback, "Server router: FreeBuff exhaust-first guardian (8635.js)")

    # 8c. Ensure 9Router DB providerStrategies reflects fill-first
    try:
        import sqlite3, json
        db_path = os.path.expanduser("~/.9router/db/data.sqlite")
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT data FROM settings WHERE id = 1")
            row = cur.fetchone()
            if row:
                st = json.loads(row[0])
                ps = st.setdefault("providerStrategies", {})
                ps["openai-compatible-chat-freebuff"] = {
                    "fallbackStrategy": "fill-first"
                }
                cur.execute("UPDATE settings SET data = ? WHERE id = 1", (json.dumps(st),))
                conn.commit()
                print("  [✓] DB settings: Saved FreeBuff fallbackStrategy='fill-first'")
            conn.close()
    except Exception as e:
        print(f"  [!] Failed to set DB providerStrategies: {e}")

    # 8d. Ensure outbound request body model is synchronized with resolved model
    c_8895 = os.path.join(build_dir, "server/chunks/8895.js")
    if os.path.exists(c_8895):
        with open(c_8895, "r", encoding="utf-8") as f:
            c_8895_content = f.read()
        target_aimodel = 'ai.model=(ap?.startsWith?.("openai-compatible-")&&aq)?aq:(0,g.kD)(aD)'
        if target_aimodel not in c_8895_content:
            target_aimodel = 'ai.model=(0,g.kD)(aD)'
        repl_aimodel = (
            '(()=>{if(ap?.includes("freebuff")){'
            'let m={"deepseek-v4-flash":"deepseek/deepseek-v4-flash","glm-5.3-flash":"z-ai/glm-5.3-flash",'
            '"solar-pro":"upstage/solar-pro4","solar-pro4":"upstage/solar-pro4","mimo-v2.6-pro":"mimo/mimo-v2.6-pro",'
            '"mimo-v2.5":"mimo/mimo-v2.5","gpt-5.6-luna":"openai/gpt-5.6-luna","gemini-3.8-flash":"google/gemini-3.8-flash",'
            '"claude-fable-5.1":"anthropic/claude-fable-5.1","muse-spark-1.2-contributor":"meta/muse-spark-1.2-contributor"}[aq];'
            'if(m)aq=m}})(),'
            'ai.model=(ap?.startsWith?.("openai-compatible-")&&aq)?aq:(0,g.kD)(aD)'
        )
        if "deepseek/deepseek-v4-flash" not in c_8895_content:
            patch_file(c_8895, target_aimodel, repl_aimodel, "Server translator: preserve OpenAI-compatible mapped model (8895.js)")

    c_6022 = os.path.join(build_dir, "server/chunks/6022.js")
    if os.path.exists(c_6022):
        target_trans = 'transformRequest(a,b,c,d){return b}'
        repl_trans = 'transformRequest(a,b,c,d){return(this.provider?.startsWith?.("openai-compatible-")&&a&&b&&"object"==typeof b)?{...b,model:a}:b}'
        patch_file(c_6022, target_trans, repl_trans, "Server OpenAI-compatible: forward resolved model in body (6022.js)")

    print("\n[✓] FreeBuff automated login & UI/UX patching completed successfully.")
    return True

if __name__ == "__main__":
    success = run()
    sys.exit(0 if success else 1)
