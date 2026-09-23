# 9Router Web UI & Automated Device Login Guide for FreeBuff

This guide provides a transparent, easy-to-follow overview of the **FreeBuff** integration in the 9Router Web Dashboard, detailing the **Antigravity-grade automated onboarding experience**, the official high-resolution branding, and pool management.

---

## 1. Overview & Experience Comparison

Adding upstream FreeBuff/Codebuff tokens used to require tedious manual steps:
- Opening developer tools or running terminal commands to extract session tokens.
- Copying long, sensitive alphanumeric tokens.
- Navigating to manual forms and pasting tokens.

With the **FreeBuff automated Device Code integration**, onboarding is completely frictionless:

| Feature | Legacy Manual Flow | Antigravity-Style Automated Flow |
|---|---|---|
| **Interaction** | Manual CLI extraction or DevTools inspection | **1-Click in 9Router UI** |
| **Token Handling** | Manual copy-paste of raw bearer tokens | **Automatic wire exchange & direct SQLite injection** |
| **Browser Action** | Manual tab navigation | **Auto-opens Codebuff login tab simultaneously** |
| **Feedback** | Trial and error on save | **Live polling with instant "Connected Successfully!" badge** |
| **Multi-Account** | Manual priority & naming | **Auto-detected account name, email & priority sequencing** |

---

## 2. Step-by-Step Onboarding Walkthrough

### Step 1: Open FreeBuff in 9Router Dashboard
1. Open your 9Router Web Dashboard (e.g. `http://localhost:20128/dashboard/providers`).
2. Locate **FreeBuff** in the **Free Tier Providers** section.
3. Click on the provider card to view its connection management page (`/dashboard/providers/openai-compatible-chat-freebuff`).

### Step 2: Click "Add Connection"
1. Click the **Add Connection** button in the header or connection table toolbar.
2. A dedicated modal titled **"Connect FreeBuff Account"** opens immediately:
   - Displays the verification link: `https://www.codebuff.com/login?auth_code=...`
   - Displays a short verification code.
   - Provides a direct **"Open Login Page"** button.
3. **Simultaneously**, 9Router automatically opens the Codebuff authentication page in a new browser tab.

### Step 3: Complete Authentication
1. In the newly opened tab, sign in with your GitHub account.
2. Authorize Codebuff (takes ~2 seconds).

### Step 4: Automatic Enrollment
1. 9Router's background worker polls `/api/oauth/freebuff/poll` every 3 seconds.
2. As soon as authorization completes upstream:
   - 9Router securely receives the account session token and email address.
   - The connection is automatically stored into 9Router's SQLite database (`~/.9router/db/data.sqlite`).
   - The modal updates in real-time to **"Connected Successfully!"** with a green checkmark.
3. Upon closing the modal, the dashboard refreshes automatically, displaying your new active connection in the pool!

---

## 3. Official Visual Identity & High-Resolution Branding

The provider includes the authentic, canonical **FreeBuff brand identity** extracted directly from `freebuff.com`:
- **Design Motif**: A sleek black rounded square (squircle) enclosing the official geometric white **F** glyph composed of two interlocking L-shaped ribbons.
- **Color Scheme**: High-contrast pure white glyphs (`#FFFFFF`) against a deep dark background (`#000000`), with transparent outer corners.
- **Assets Provided**:
  - `assets/freebuff.svg`: Scalable vector source reproducing the official SVG path with decimal precision (96.9% IoU overlap with the official web icon).
  - `assets/freebuff.png` (512x512): Ultra high-resolution raster image with crystal-clear edges and full alpha transparency.
  - Multi-resolution variants: `freebuff-256.png` (256x256), `freebuff-128.png` (128x128), and `freebuff-32.png` (32x32).
- **Dashboard Display**: Served natively from 9Router's static provider registry at `/providers/freebuff.png`.

---

## 4. Antigravity-Grade Available Models UI & Control

The FreeBuff provider page features the exact **Antigravity-grade Available Models interface** rather than generic OpenAI tables:

1. **Card Grid Layout**:
   - Each model is displayed as an individual card with a robot avatar, monospace model path pill (e.g. `freebuff/deepseek/deepseek-v4-flash`), friendly title, and capability badges (Vision, Reasoning, Tool Calling).
   - Fast one-click **Copy** button on each card.
2. **Batch Controls ("Active All" / "Disable All")**:
   - Header buttons allow disabling or activating all catalog models in one click with confirmation.
3. **Interactive Model Disabling & Restoration**:
   - Hovering any model card reveals the **Disable** action (`close` icon), immediately moving it to the disabled section.
   - Disabled models appear under the **"Disabled models (N):"** section as dashed pills (e.g. `+ mimo/mimo-v2.6-pro`). Clicking a pill instantly restores the model back to the active grid.
4. **Instant Synchronous Enforcement**:
   - Disabling a model removes it from 9Router's `/v1/models` endpoint immediately and causes router-level requests for that model to be rejected with HTTP 400.
   - Restoring a model restores it to `/v1/models` and enables routing without requiring server restarts.
5. **Short-Name Aliasing**:
   - Built-in router mapping automatically routes both standard short names (`deepseek-v4-flash`, `glm-5.3-flash`, `solar-pro`) and upstream paths (`deepseek/deepseek-v4-flash`, `z-ai/glm-5.3-flash`, `upstage/solar-pro4`) to upstream FreeBuff destinations.

---

## 5. Multi-Account Management & Pool Operations

### Traffic Rotation
- Each connected account provides an allowance of **300 freebucks per day** across free models (GLM 5.3 Flash, DeepSeek V4 Flash, Solar Pro, MiMo, etc.).
- 9Router balances requests across all active connections.

### Connection Operations
- **Reordering (Priority)**: Use the up/down arrows in the table to change account priority order.
- **Enable / Disable Toggle**: Click the switch next to any connection to temporarily disable or enable it without deleting the token.
- **Zero-Cost Live Healthcheck**: Click the test icon on any connection to verify its token upstream via `GET /v1/models` without consuming any session freebucks.
- **Deletion**: Click the delete icon to remove a connection when an account is retired.

---

## 6. Automated Installation & Update Survivability

The UI enhancements are applied via `patch-9router-ui.py`:
- **Syntax Verification**: Every modified file is strictly pre-validated with `node -c`. If any syntax mismatch occurs, changes are rolled back immediately.
- **Persistence Across Updates**: Integrated into system maintenance hooks (`apply_9router_fixes.py`), ensuring that when `npm i -g 9router` updates the core package, the FreeBuff UI and device login flow are automatically re-applied.
