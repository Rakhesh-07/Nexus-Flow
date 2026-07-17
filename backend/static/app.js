// AIFlow Frontend Application Logic

// App State
const state = {
    token: localStorage.getItem("aiflow_token") || null,
    user: null, // { username, role }
    activeView: "chat",
    uploadQueue: [],
    conversations: [],
    currentConversationId: null
};

// Base API URL path helper
const API_BASE = "";

// Page Load Lifecycle
document.addEventListener("DOMContentLoaded", () => {
    initAuth();
});

// --- AUTHENTICATION & LOGIN MANAGEMENT ---

function initAuth() {
    if (state.token) {
        // Decode token payload locally to retrieve user details
        try {
            const payload = JSON.parse(atob(state.token.split('.')[1]));
            state.user = {
                username: payload.sub,
                role: payload.role || (payload.sub.toLowerCase() === "admin" ? "admin" : "user")
            };
            
            // Show dashboard, hide auth card
            document.getElementById("auth-view").classList.add("hidden");
            document.getElementById("dashboard-view").classList.remove("hidden");
            
            // Set user profile info in DOM
            document.getElementById("current-username").textContent = state.user.username;
            
            // Set role badge classes and text
            const badge = document.getElementById("user-role-badge");
            badge.textContent = state.user.role;
            if (state.user.role === "admin") {
                badge.className = "badge badge-admin";
            } else {
                badge.className = "badge badge-user";
            }
            
            switchView(state.activeView);
        } catch (e) {
            console.error("Failed to parse local JWT token:", e);
            handleLogout();
        }
    } else {
        // Show auth card, hide dashboard
        document.getElementById("auth-view").classList.remove("hidden");
        document.getElementById("dashboard-view").classList.add("hidden");
    }
}

function switchAuthTab(tab) {
    const loginForm = document.getElementById("login-form");
    const registerForm = document.getElementById("register-form");
    const loginTabBtn = document.getElementById("tab-login-btn");
    const registerTabBtn = document.getElementById("tab-register-btn");
    const errDiv = document.getElementById("auth-error");
    
    errDiv.classList.add("hidden");

    if (tab === "login") {
        loginForm.classList.remove("hidden");
        registerForm.classList.add("hidden");
        loginTabBtn.classList.add("active");
        registerTabBtn.classList.remove("active");
    } else {
        loginForm.classList.add("hidden");
        registerForm.classList.remove("hidden");
        loginTabBtn.classList.remove("active");
        registerTabBtn.classList.add("active");
    }
}

async function handleLogin(event) {
    event.preventDefault();
    const usernameInput = document.getElementById("login-username").value.trim();
    const passwordInput = document.getElementById("login-password").value;
    const errDiv = document.getElementById("auth-error");
    errDiv.classList.add("hidden");

    // OAuth2PasswordRequestForm expects url-encoded payload
    const formData = new URLSearchParams();
    formData.append("username", usernameInput);
    formData.append("password", passwordInput);

    try {
        const response = await fetch(`${API_BASE}/login`, {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: formData
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || "Authentication failed. Check credentials.");
        }

        const data = await response.json();
        localStorage.setItem("aiflow_token", data.access_token);
        state.token = data.access_token;
        
        // Initialize
        document.getElementById("login-form").reset();
        initAuth();
    } catch (e) {
        errDiv.textContent = e.message;
        errDiv.classList.remove("hidden");
    }
}

async function handleRegister(event) {
    event.preventDefault();
    const usernameInput = document.getElementById("register-username").value.trim();
    const passwordInput = document.getElementById("register-password").value;
    const roleSelect = document.getElementById("register-role").value;
    const errDiv = document.getElementById("auth-error");
    errDiv.classList.add("hidden");

    try {
        const response = await fetch(`${API_BASE}/register`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                username: usernameInput,
                password: passwordInput,
                role: roleSelect
            })
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || "Account registration failed.");
        }
        
        // Alert and switch to login
        alert("Account registered successfully! Please log in.");
        document.getElementById("register-form").reset();
        switchAuthTab("login");
        document.getElementById("login-username").value = usernameInput;
    } catch (e) {
        errDiv.textContent = e.message;
        errDiv.classList.remove("hidden");
    }
}

function handleLogout() {
    localStorage.removeItem("aiflow_token");
    state.token = null;
    state.user = null;
    state.activeView = "chat";
    state.currentConversationId = null;
    document.getElementById("chat-messages").innerHTML = "";
    
    // Clear credentials forms explicitly to prevent autofill retention
    try {
        document.getElementById("login-form").reset();
        document.getElementById("register-form").reset();
    } catch (e) {
        console.error("Form reset failed:", e);
    }
    
    initAuth();
}

// --- SIDEBAR VIEW SWITCHING ---

function switchView(viewName) {
    state.activeView = viewName;
    
    // Hide all sections
    document.querySelectorAll(".content-section").forEach(sec => sec.classList.add("hidden"));
    
    // De-activate all sidebar nav items
    document.querySelectorAll(".nav-item").forEach(item => item.classList.remove("active"));
    
    // Map view names to elements
    const sections = {
        chat: "chat-section",
        upload: "upload-section",
        analytics: "analytics-section"
    };
    
    document.getElementById(sections[viewName]).classList.remove("hidden");
    
    // Find index of clicked nav item
    const navItems = document.querySelectorAll(".nav-item");
    if (viewName === "chat") navItems[0].classList.add("active");
    if (viewName === "upload") navItems[1].classList.add("active");
    if (viewName === "analytics") {
        navItems[2].classList.add("active");
        loadAnalytics();
    }
}

// --- CHAT SWARM WORKFLOW RUNS ---

async function handleSendMessage(event) {
    event.preventDefault();
    const chatInput = document.getElementById("chat-input");
    const query = chatInput.value.trim();
    if (!query) return;

    chatInput.value = "";
    
    // 1. Render User Message Bubble
    appendMessage("user", query);
    
    // 2. Show Typing Loader Indicator
    const loaderId = appendTypingIndicator();
    
    try {
        const response = await fetch(`${API_BASE}/query`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${state.token}`
            },
            body: JSON.stringify({
                query: query,
                conversation_id: state.currentConversationId
            })
        });

        // Remove Loader
        removeElement(loaderId);

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Orchestration crashed.");
        }

        const data = await response.json();
        
        // Save conversation context ID
        state.currentConversationId = data.conversation_id;
        
        // 3. Render Agent Response Bubble
        appendAgentResponse(data);
    } catch (e) {
        removeElement(loaderId);
        appendMessage("agent", `Error: ${e.message}`);
    }
}

function appendMessage(sender, text) {
    const messagesArea = document.getElementById("chat-messages");
    const msgDiv = document.createElement("div");
    msgDiv.className = `message ${sender}`;
    
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text;
    
    msgDiv.appendChild(bubble);
    messagesArea.appendChild(msgDiv);
    
    // Auto-scroll
    messagesArea.scrollTop = messagesArea.scrollHeight;
}

function appendTypingIndicator() {
    const messagesArea = document.getElementById("chat-messages");
    const loaderId = "typing_loader_" + Date.now();
    
    const msgDiv = document.createElement("div");
    msgDiv.className = "message agent";
    msgDiv.id = loaderId;
    
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.innerHTML = `<span class="typing-dots">Orchestrator thinking...</span>`;
    
    msgDiv.appendChild(bubble);
    messagesArea.appendChild(msgDiv);
    messagesArea.scrollTop = messagesArea.scrollHeight;
    
    return loaderId;
}

function removeElement(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

function appendAgentResponse(data) {
    const messagesArea = document.getElementById("chat-messages");
    const msgDiv = document.createElement("div");
    msgDiv.className = "message agent";
    
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    
    const explanation = data.response?.explanation || "No explanation text generated.";
    bubble.innerHTML = `<p>${explanation}</p>`;
    
    // Citations section
    const citations = data.response?.citations || [];
    if (citations.length > 0) {
        const citTitle = document.createElement("p");
        citTitle.style.marginTop = "10px";
        citTitle.style.fontWeight = "600";
        citTitle.textContent = "Citations:";
        bubble.appendChild(citTitle);
        
        const citList = document.createElement("ul");
        citList.className = "citations-list";
        citations.forEach(c => {
            const li = document.createElement("li");
            li.textContent = c;
            citList.appendChild(li);
        });
        bubble.appendChild(citList);
    }
    
    // Recommendations section
    const recommendations = data.response?.recommendations || [];
    if (recommendations.length > 0) {
        const recTitle = document.createElement("p");
        recTitle.style.marginTop = "10px";
        recTitle.style.fontWeight = "600";
        recTitle.textContent = "Recommendations:";
        bubble.appendChild(recTitle);
        
        const recList = document.createElement("ul");
        recList.className = "recs-list";
        recommendations.forEach(r => {
            const li = document.createElement("li");
            li.textContent = r;
            recList.appendChild(li);
        });
        bubble.appendChild(recList);
    }
    
    msgDiv.appendChild(bubble);
    
    // Metadata tags
    const metaContainer = document.createElement("div");
    metaContainer.className = "message-meta";
    
    // Latency
    const latencyTag = document.createElement("span");
    latencyTag.className = "meta-tag";
    latencyTag.textContent = `Latency: ${data.execution_time_ms} ms`;
    metaContainer.appendChild(latencyTag);
    
    // Confidence Score
    const confidenceTag = document.createElement("span");
    confidenceTag.className = "meta-tag meta-tag-green";
    confidenceTag.textContent = `Confidence: ${Math.round(data.confidence_score * 100)}%`;
    metaContainer.appendChild(confidenceTag);
    
    // Token details
    if (data.total_tokens !== undefined) {
        const tokenTag = document.createElement("span");
        tokenTag.className = "meta-tag meta-tag-blue";
        tokenTag.textContent = `Tokens: ${data.total_tokens} (P:${data.prompt_tokens} / C:${data.completion_tokens})`;
        metaContainer.appendChild(tokenTag);
    }
    
    msgDiv.appendChild(metaContainer);
    messagesArea.appendChild(msgDiv);
    messagesArea.scrollTop = messagesArea.scrollHeight;
}

// --- RAG DOCUMENT FILE UPLOADER ---

function triggerFileSelect() {
    document.getElementById("file-input").click();
}

function handleFileSelect(event) {
    const files = event.target.files;
    addFilesToQueue(files);
}

function addFilesToQueue(files) {
    for (let i = 0; i < files.length; i++) {
        // Avoid duplicate queue entries
        if (!state.uploadQueue.some(f => f.name === files[i].name && f.size === files[i].size)) {
            state.uploadQueue.push(files[i]);
        }
    }
    renderFileQueue();
}

function renderFileQueue() {
    const list = document.getElementById("file-list");
    const container = document.getElementById("file-queue-container");
    
    if (state.uploadQueue.length === 0) {
        container.classList.add("hidden");
        return;
    }
    
    list.innerHTML = "";
    container.classList.remove("hidden");
    
    state.uploadQueue.forEach((file, index) => {
        const item = document.createElement("div");
        item.className = "file-item";
        
        const nameSpan = document.createElement("span");
        nameSpan.className = "file-name";
        nameSpan.textContent = file.name;
        
        const sizeSpan = document.createElement("span");
        sizeSpan.className = "file-size";
        sizeSpan.textContent = formatBytes(file.size);
        
        const removeBtn = document.createElement("span");
        removeBtn.style.color = "var(--danger)";
        removeBtn.style.cursor = "pointer";
        removeBtn.textContent = " ✕";
        removeBtn.onclick = (e) => {
            e.stopPropagation();
            removeFileFromQueue(index);
        };
        
        const leftDiv = document.createElement("div");
        leftDiv.appendChild(nameSpan);
        leftDiv.appendChild(document.createTextNode(" "));
        leftDiv.appendChild(sizeSpan);
        
        item.appendChild(leftDiv);
        item.appendChild(removeBtn);
        list.appendChild(item);
    });
}

function removeFileFromQueue(index) {
    state.uploadQueue.splice(index, 1);
    renderFileQueue();
}

function clearFileQueue() {
    state.uploadQueue = [];
    renderFileQueue();
    document.getElementById("upload-status").classList.add("hidden");
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Upload queued files sequentially
async statusDiv => {}
async function uploadQueuedFiles() {
    if (state.uploadQueue.length === 0) return;
    
    const statusDiv = document.getElementById("upload-status");
    const heading = document.getElementById("status-heading");
    const bar = document.getElementById("status-progress-bar");
    const details = document.getElementById("status-details");
    
    statusDiv.classList.remove("hidden");
    bar.style.width = "0%";
    heading.textContent = "Uploading Documents...";
    
    const filesToUpload = [...state.uploadQueue];
    let completedCount = 0;
    
    for (let i = 0; i < filesToUpload.length; i++) {
        const file = filesToUpload[i];
        details.textContent = `Processing file ${i + 1} of ${filesToUpload.length}: ${file.name}...`;
        
        const formData = new FormData();
        formData.append("file", file);
        
        try {
            const response = await fetch(`${API_BASE}/upload`, {
                method: "POST",
                headers: { "Authorization": `Bearer ${state.token}` },
                body: formData
            });
            
            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || "Upload failed");
            }
            
            completedCount++;
            const pct = Math.round((completedCount / filesToUpload.length) * 100);
            bar.style.width = `${pct}%`;
        } catch (e) {
            details.innerHTML += `<br><span style="color: var(--danger)">Failed to process '${file.name}': ${e.message}</span>`;
        }
    }
    
    heading.textContent = "Process Complete";
    details.innerHTML = `<span class="text-success" style="font-weight: 600;">Vector DB updated successfully!</span> All ${completedCount} documents parsed, chunked, and indexed.`;
    
    // Reset file queue
    state.uploadQueue = [];
    renderFileQueue();
}

// --- USAGE ANALYTICS LOGIC ---

async function loadAnalytics() {
    try {
        const response = await fetch(`${API_BASE}/analytics`, {
            method: "GET",
            headers: { "Authorization": `Bearer ${state.token}` }
        });
        
        if (!response.ok) {
            throw new Error("Failed to load analytics summaries.");
        }
        
        const data = await response.json();
        
        if (data.role === "admin") {
            // Render Admin Dashboard and stats
            document.getElementById("admin-analytics").classList.remove("hidden");
            renderAdminStats(data);
        } else {
            // Render User stats
            document.getElementById("admin-analytics").classList.add("hidden");
        }
        
        renderUserStats(data);
    } catch (e) {
        console.error(e);
        alert(e.message);
    }
}

function renderUserStats(data) {
    const stats = data.role === "admin" ? data.global_stats : data.stats;
    const history = data.role === "admin" ? [] : (data.history || []);
    
    // Cards
    document.getElementById("user-total-queries").textContent = stats.total_queries !== undefined ? stats.total_queries : stats.query_count;
    document.getElementById("user-total-documents").textContent = stats.total_documents !== undefined ? stats.total_documents : stats.document_count;
    document.getElementById("user-total-tokens").textContent = stats.total_tokens;
    
    // Query History Table (only populated/visible in regular user data payload)
    const tbody = document.getElementById("user-history-tbody");
    tbody.innerHTML = "";
    
    if (data.role === "admin") {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center" style="color: var(--text-muted)">Viewing as Admin. History Breakdown is listed below in user detail.</td></tr>`;
        return;
    }
    
    if (history.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center">No queries run yet. Use the Chat Swarm to execute query workflows.</td></tr>`;
        return;
    }
    
    history.forEach(row => {
        const tr = document.createElement("tr");
        
        const date = new Date(row.created_at).toLocaleString();
        
        tr.innerHTML = `
            <td>${date}</td>
            <td style="max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${row.query}</td>
            <td><span class="badge ${row.status === 'success' ? 'badge-admin' : 'badge-user'}">${row.status}</span></td>
            <td>${row.total_tokens}</td>
            <td>${row.execution_time_ms} ms</td>
        `;
        tbody.appendChild(tr);
    });
}

function renderAdminStats(data) {
    const global = data.global_stats;
    const users = data.users_stats || [];
    
    // Global Dashboard Cards
    document.getElementById("admin-total-queries").textContent = global.total_queries;
    document.getElementById("admin-total-documents").textContent = global.total_documents;
    document.getElementById("admin-total-cost").textContent = `$${global.estimated_cost_usd.toFixed(4)}`;
    document.getElementById("admin-avg-latency").textContent = `${global.average_latency_ms} ms`;
    
    // User stats list
    const tbody = document.getElementById("admin-users-tbody");
    tbody.innerHTML = "";
    
    if (users.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center">No platform users found.</td></tr>`;
        return;
    }
    
    users.forEach(u => {
        const date = new Date(u.last_active).toLocaleString();
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${u.user_id}</td>
            <td><strong>${u.username}</strong></td>
            <td><span class="badge ${u.role === 'admin' ? 'badge-admin' : 'badge-user'}">${u.role}</span></td>
            <td>${u.query_count}</td>
            <td>${u.document_count}</td>
            <td>${u.total_tokens} (P:${u.prompt_tokens} / C:${u.completion_tokens})</td>
            <td>${date}</td>
        `;
        tbody.appendChild(tr);
    });
}
