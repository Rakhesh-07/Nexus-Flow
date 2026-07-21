// NexusFlow Enterprise Frontend Controller
const API_BASE = ""; // Relative path to FastAPI backend

const state = {
    token: localStorage.getItem("nexusflow_token") || null,
    user: null,
    activeView: "chat"
};

// Initialize Application State on Load
document.addEventListener("DOMContentLoaded", () => {
    initAuth();
});

function initAuth() {
    if (state.token) {
        fetchUserProfile();
    } else {
        showAuthView();
    }
}

function showAuthView() {
    document.getElementById("auth-view").classList.remove("hidden");
    document.getElementById("dashboard-view").classList.add("hidden");
}

function showDashboardView() {
    document.getElementById("auth-view").classList.add("hidden");
    document.getElementById("dashboard-view").classList.remove("hidden");
    
    // Update Header Profile & Role Badges
    if (state.user) {
        document.getElementById("current-username").textContent = state.user.username;
        document.getElementById("user-role-badge").textContent = formatRole(state.user.role);
        document.getElementById("user-dept-badge").textContent = state.user.department || "General";
        document.getElementById("current-clearance").textContent = state.user.clearance_level || "INTERNAL";

        // Pre-fill Self Service Profile Form
        document.getElementById("profile-fullname").value = state.user.full_name || "";
        document.getElementById("profile-email").value = state.user.email || "";
        document.getElementById("profile-contact").value = state.user.contact_details || "";
    }

    // Adjust Nav Items according to Role
    configureNavigationByRole();

    // Default View
    switchView("chat");
}

function formatRole(role) {
    if (!role) return "User";
    const map = {
        "super_admin": "Super Admin",
        "department_manager": "Dept Manager",
        "team_lead": "Team Lead",
        "employee": "Employee",
        "guest": "Guest"
    };
    return map[role.toLowerCase()] || role;
}

function configureNavigationByRole() {
    const role = (state.user && state.user.role) ? state.user.role.toLowerCase() : "guest";
    
    const navUpload = document.getElementById("nav-upload");
    const navPending = document.getElementById("nav-pending");
    const navAudit = document.getElementById("nav-audit");
    const navAdmin = document.getElementById("nav-admin");

    if (role === "guest") {
        navUpload.classList.add("hidden");
        navPending.classList.add("hidden");
        navAudit.classList.add("hidden");
        navAdmin.classList.add("hidden");
    } else if (role === "super_admin") {
        navUpload.classList.remove("hidden");
        navPending.classList.remove("hidden");
        navAudit.classList.remove("hidden");
        navAdmin.classList.remove("hidden");
    } else if (role === "department_manager") {
        navUpload.classList.remove("hidden");
        navPending.classList.remove("hidden");
        navAudit.classList.remove("hidden");
        navAdmin.classList.remove("hidden");
    } else {
        // Employee & Team Lead
        navUpload.classList.remove("hidden");
        navPending.classList.add("hidden");
        navAudit.classList.add("hidden");
        navAdmin.classList.add("hidden");
    }
}

async function fetchUserProfile() {
    try {
        const response = await fetch(`${API_BASE}/me`, {
            headers: { "Authorization": `Bearer ${state.token}` }
        });
        if (!response.ok) {
            throw new Error("Session expired. Please log in again.");
        }
        state.user = await response.json();
        showDashboardView();
    } catch (e) {
        console.error(e);
        handleLogout();
    }
}

// Auth Tab Switching
function switchAuthTab(tab) {
    const loginForm = document.getElementById("login-form");
    const registerForm = document.getElementById("register-form");
    const loginTabBtn = document.getElementById("tab-login-btn");
    const registerTabBtn = document.getElementById("tab-register-btn");

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
            throw new Error(data.detail || "Authentication failed.");
        }

        const data = await response.json();
        localStorage.setItem("nexusflow_token", data.access_token);
        state.token = data.access_token;
        
        document.getElementById("login-form").reset();
        await fetchUserProfile();
    } catch (e) {
        errDiv.textContent = e.message;
        errDiv.classList.remove("hidden");
    }
}

async function handleRegister(event) {
    event.preventDefault();
    const usernameInput = document.getElementById("register-username").value.trim();
    const passwordInput = document.getElementById("register-password").value;
    const deptSelect = document.getElementById("register-department").value;
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
                department: deptSelect,
                role: roleSelect
            })
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || "Registration failed.");
        }

        alert("Enterprise account created successfully! Please log in.");
        document.getElementById("register-form").reset();
        switchAuthTab("login");
        document.getElementById("login-username").value = usernameInput;
    } catch (e) {
        errDiv.textContent = e.message;
        errDiv.classList.remove("hidden");
    }
}

function handleLogout() {
    localStorage.removeItem("nexusflow_token");
    state.token = null;
    state.user = null;
    state.activeView = "chat";
    document.getElementById("chat-messages").innerHTML = "";
    
    try {
        document.getElementById("login-form").reset();
        document.getElementById("register-form").reset();
    } catch (e) {
        console.error("Form reset:", e);
    }
    
    showAuthView();
}

// Navigation View Switcher
function switchView(viewName) {
    state.activeView = viewName;
    
    const sections = ["chat", "documents", "upload", "pending", "profile", "analytics", "audit", "admin-dashboard"];
    sections.forEach(s => {
        const secEl = document.getElementById(`${s}-section`);
        const navEl = document.getElementById(`nav-${s}`);
        if (secEl) {
            if (s === viewName) {
                secEl.classList.remove("hidden");
            } else {
                secEl.classList.add("hidden");
            }
        }
        if (navEl) {
            if (s === viewName) {
                navEl.classList.add("active");
            } else {
                navEl.classList.remove("active");
            }
        }
    });

    if (viewName === "documents") fetchDocumentsLibrary();
    if (viewName === "pending") fetchPendingApprovals();
    if (viewName === "analytics") fetchAnalytics();
    if (viewName === "audit") fetchAuditLogs();
    if (viewName === "admin-dashboard") fetchAdminDashboard();
}

// SELF-SERVICE PROFILE & PASSWORD UPDATES
async function handleUpdateProfile(event) {
    event.preventDefault();
    const fullName = document.getElementById("profile-fullname").value.trim();
    const email = document.getElementById("profile-email").value.trim();
    const contact = document.getElementById("profile-contact").value.trim();

    try {
        const response = await fetch(`${API_BASE}/me/profile`, {
            method: "PUT",
            headers: {
                "Authorization": `Bearer ${state.token}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                full_name: fullName,
                email: email,
                contact_details: contact
            })
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || "Profile update failed.");
        }

        state.user = await response.json();
        alert("✓ Your basic profile information has been updated successfully.");
    } catch (e) {
        alert(`Error: ${e.message}`);
    }
}

async function handleChangePassword(event) {
    event.preventDefault();
    const currentPassword = document.getElementById("pwd-current").value;
    const newPassword = document.getElementById("pwd-new").value;

    try {
        const response = await fetch(`${API_BASE}/me/password`, {
            method: "PUT",
            headers: {
                "Authorization": `Bearer ${state.token}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                current_password: currentPassword,
                new_password: newPassword
            })
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || "Password change failed.");
        }

        alert("✓ Password updated successfully! Please log in with your new password.");
        document.getElementById("password-form").reset();
    } catch (e) {
        alert(`Password Error: ${e.message}`);
    }
}

// CHAT SWARM
async function handleSendMessage(event) {
    event.preventDefault();
    const input = document.getElementById("chat-input");
    const query = input.value.trim();
    if (!query) return;

    input.value = "";
    appendChatMessage("user", query);

    const loaderId = appendLoadingMessage();

    try {
        const response = await fetch(`${API_BASE}/query`, {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${state.token}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ query: query, conversation_id: null })
        });

        removeLoadingMessage(loaderId);

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || "Query failed");
        }

        const data = await response.json();
        renderAssistantResponse(data);

    } catch (e) {
        removeLoadingMessage(loaderId);
        appendChatMessage("system", `Error: ${e.message}`);
    }
}

function appendChatMessage(role, text) {
    const chatBox = document.getElementById("chat-messages");
    const msgDiv = document.createElement("div");
    msgDiv.className = `message ${role}-message`;
    msgDiv.innerHTML = `<p>${escapeHtml(text)}</p>`;
    chatBox.appendChild(msgDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function appendLoadingMessage() {
    const chatBox = document.getElementById("chat-messages");
    const id = "loader-" + Date.now();
    const msgDiv = document.createElement("div");
    msgDiv.id = id;
    msgDiv.className = "message system-message loading-pulse";
    msgDiv.innerHTML = `<p>⚡ NexusFlow Swarms Orchestrating & Querying Vector DB...</p>`;
    chatBox.appendChild(msgDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
    return id;
}

function removeLoadingMessage(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

function renderAssistantResponse(data) {
    const chatBox = document.getElementById("chat-messages");
    const msgDiv = document.createElement("div");
    msgDiv.className = "message assistant-message card";

    const respObj = data.response || {};
    const explanation = respObj.explanation || "No answer text generated.";
    const citations = respObj.citations || [];
    const recommendations = respObj.recommendations || [];

    let html = `<div class="response-body"><p>${escapeHtml(explanation)}</p></div>`;

    if (citations.length > 0) {
        html += `<div class="citations-area"><strong>Citations:</strong> <ul>`;
        citations.forEach(c => {
            html += `<li>📄 ${escapeHtml(c)}</li>`;
        });
        html += `</ul></div>`;
    }

    if (recommendations.length > 0) {
        html += `<div class="recommendations-area"><strong>Recommendations:</strong> <ul>`;
        recommendations.forEach(r => {
            html += `<li>💡 ${escapeHtml(r)}</li>`;
        });
        html += `</ul></div>`;
    }

    html += `<div class="metrics-footer">
        <span class="meta-tag">Latency: ${data.execution_time_ms} ms</span>
        <span class="meta-tag">Confidence: ${(data.confidence_score * 100).toFixed(0)}%</span>
        <span class="meta-tag">Tokens: ${data.total_tokens} (P:${data.prompt_tokens} / C:${data.completion_tokens})</span>
    </div>`;

    msgDiv.innerHTML = html;
    chatBox.appendChild(msgDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
}

// ACCESSIBLE DOCUMENT LIBRARY
async function fetchDocumentsLibrary() {
    const tbody = document.getElementById("documents-tbody");
    tbody.innerHTML = `<tr><td colspan="7" class="text-center">Loading authorized document library...</td></tr>`;

    try {
        const response = await fetch(`${API_BASE}/documents`, {
            headers: { "Authorization": `Bearer ${state.token}` }
        });
        if (!response.ok) throw new Error("Failed to load documents.");
        const docs = await response.json();

        if (docs.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center">No accessible documents found under your department and clearance level.</td></tr>`;
            return;
        }

        let html = "";
        docs.forEach(doc => {
            const classPill = `<span class="class-pill class-${doc.classification}">${doc.classification}</span>`;
            const appBadge = doc.approved ? `<span class="text-success">✓ Approved</span>` : `<span style="color:#ffaa00;">⏳ Pending Approval</span>`;
            
            html += `<tr>
                <td><strong>${escapeHtml(doc.filename)}</strong></td>
                <td>${escapeHtml(doc.department)}</td>
                <td>${classPill}</td>
                <td>${escapeHtml(doc.visibility)}</td>
                <td>${escapeHtml(doc.owner_username)}</td>
                <td>${appBadge}</td>
                <td>
                    <button class="btn btn-secondary btn-sm btn-danger" onclick="deleteDocument(${doc.id})">Delete</button>
                </td>
            </tr>`;
        });
        tbody.innerHTML = html;
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center error-msg">${e.message}</td></tr>`;
    }
}

async function deleteDocument(docId) {
    if (!confirm("Are you sure you want to delete this document and remove its vectors from ChromaDB?")) return;

    try {
        const response = await fetch(`${API_BASE}/documents/${docId}`, {
            method: "DELETE",
            headers: { "Authorization": `Bearer ${state.token}` }
        });
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || "Deletion failed.");
        }
        alert("Document deleted successfully.");
        fetchDocumentsLibrary();
    } catch (e) {
        alert(`Error: ${e.message}`);
    }
}

// UPLOAD DOCUMENT WITH METADATA
function triggerFileSelect() {
    document.getElementById("file-input").click();
}

function handleFileSelect(event) {
    const files = event.target.files;
    if (files.length > 0) {
        document.getElementById("selected-file-name").textContent = files[0].name;
    }
}

async function handleUploadSubmit(event) {
    event.preventDefault();
    const fileInput = document.getElementById("file-input");
    if (!fileInput.files || fileInput.files.length === 0) {
        alert("Please select a file to upload.");
        return;
    }

    const file = fileInput.files[0];
    const dept = document.getElementById("upload-department").value;
    const classification = document.getElementById("upload-classification").value;
    const visibility = document.getElementById("upload-visibility").value;

    const formData = new FormData();
    formData.append("file", file);
    formData.append("department", dept);
    formData.append("classification", classification);
    formData.append("visibility", visibility);

    const statusDiv = document.getElementById("upload-status");
    const statusDetails = document.getElementById("status-details");
    statusDiv.classList.remove("hidden");
    statusDetails.textContent = `Uploading ${file.name} to ${dept} department...`;

    try {
        const response = await fetch(`${API_BASE}/upload`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${state.token}` },
            body: formData
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || "Upload failed.");
        }

        const resData = await response.json();
        statusDetails.textContent = `✓ ${resData.message}`;
        alert(`Success: ${resData.message}`);

        document.getElementById("upload-form").reset();
        document.getElementById("selected-file-name").textContent = "Choose File";
        setTimeout(() => statusDiv.classList.add("hidden"), 4000);

    } catch (e) {
        statusDetails.textContent = `❌ Upload Failed: ${e.message}`;
        alert(`Upload Error: ${e.message}`);
    }
}

// PENDING APPROVALS
async function fetchPendingApprovals() {
    const tbody = document.getElementById("pending-tbody");
    tbody.innerHTML = `<tr><td colspan="7" class="text-center">Loading pending approvals...</td></tr>`;

    try {
        const response = await fetch(`${API_BASE}/documents/pending`, {
            headers: { "Authorization": `Bearer ${state.token}` }
        });
        if (!response.ok) throw new Error("Could not load pending approvals.");
        const pending = await response.json();

        if (pending.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center">No pending document approvals.</td></tr>`;
            return;
        }

        let html = "";
        pending.forEach(doc => {
            html += `<tr>
                <td>${doc.id}</td>
                <td><strong>${escapeHtml(doc.filename)}</strong></td>
                <td>${escapeHtml(doc.department)}</td>
                <td><span class="class-pill class-${doc.classification}">${doc.classification}</span></td>
                <td>${escapeHtml(doc.uploaded_by_username)}</td>
                <td>${new Date(doc.created_at).toLocaleDateString()}</td>
                <td>
                    <button class="btn btn-primary btn-sm" onclick="approveDocument(${doc.id})">✓ Approve & Index</button>
                </td>
            </tr>`;
        });
        tbody.innerHTML = html;
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center error-msg">${e.message}</td></tr>`;
    }
}

async function approveDocument(docId) {
    try {
        const response = await fetch(`${API_BASE}/documents/${docId}/approve`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${state.token}` }
        });
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || "Approval failed.");
        }
        const data = await response.json();
        alert(`Document approved! ${data.chunks_indexed} vector chunks indexed into ChromaDB.`);
        fetchPendingApprovals();
    } catch (e) {
        alert(`Approval Error: ${e.message}`);
    }
}

// USAGE ANALYTICS
async function fetchAnalytics() {
    try {
        const response = await fetch(`${API_BASE}/analytics`, {
            headers: { "Authorization": `Bearer ${state.token}` }
        });
        if (!response.ok) throw new Error("Failed to fetch analytics.");
        const data = await response.json();

        const stats = data.stats || {};
        document.getElementById("user-total-queries").textContent = stats.query_count || 0;
        document.getElementById("user-total-documents").textContent = stats.document_count || 0;
        document.getElementById("user-total-tokens").textContent = (stats.total_tokens || 0).toLocaleString();

        const tbody = document.getElementById("user-history-tbody");
        const history = data.history || [];

        if (history.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" class="text-center">No queries logged yet.</td></tr>`;
            return;
        }

        let html = "";
        history.forEach(h => {
            html += `<tr>
                <td>${new Date(h.created_at).toLocaleString()}</td>
                <td>${escapeHtml(h.query)}</td>
                <td><span class="text-success">${h.status}</span></td>
                <td>${h.total_tokens}</td>
                <td>${h.execution_time_ms} ms</td>
            </tr>`;
        });
        tbody.innerHTML = html;

    } catch (e) {
        console.error(e);
    }
}

// AUDIT LOGS
async function fetchAuditLogs() {
    const tbody = document.getElementById("audit-tbody");
    tbody.innerHTML = `<tr><td colspan="7" class="text-center">Loading security audit records...</td></tr>`;

    try {
        const response = await fetch(`${API_BASE}/api/audit-logs`, {
            headers: { "Authorization": `Bearer ${state.token}` }
        });
        if (!response.ok) throw new Error("Access denied to audit logs.");
        const logs = await response.json();

        if (logs.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center">No audit records logged.</td></tr>`;
            return;
        }

        let html = "";
        logs.forEach(l => {
            const statusStyle = l.status === "SUCCESS" ? "color:#00ff66;" : l.status === "DENIED" ? "color:#ff0055;font-weight:bold;" : "color:#ffaa00;";
            html += `<tr>
                <td>${new Date(l.timestamp).toLocaleString()}</td>
                <td><strong>${escapeHtml(l.username)}</strong></td>
                <td>${escapeHtml(l.department)}</td>
                <td>${escapeHtml(l.action)}</td>
                <td>${escapeHtml(l.target_document_title)}</td>
                <td><span style="${statusStyle}">${l.status}</span></td>
                <td><code>${l.ip_address}</code></td>
            </tr>`;
        });
        tbody.innerHTML = html;

    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center error-msg">${e.message}</td></tr>`;
    }
}

// ENTERPRISE ADMIN DASHBOARD & USER MANAGEMENT
let currentAdminUsers = [];

async function fetchAdminDashboard() {
    try {
        const response = await fetch(`${API_BASE}/api/admin/dashboard`, {
            headers: { "Authorization": `Bearer ${state.token}` }
        });
        if (!response.ok) throw new Error("Access denied to Admin Dashboard.");
        const data = await response.json();

        document.getElementById("admin-card-users").textContent = data.total_users || 0;
        document.getElementById("admin-card-pending").textContent = data.pending_approvals || 0;
        document.getElementById("admin-card-restricted").textContent = data.restricted_documents || 0;
        document.getElementById("admin-card-denials").textContent = data.failed_permission_attempts || 0;

        // User Management Table (Higher Admin Only)
        const userRes = await fetch(`${API_BASE}/admin/users`, {
            headers: { "Authorization": `Bearer ${state.token}` }
        });
        if (userRes.ok) {
            currentAdminUsers = await userRes.json();
            const tbody = document.getElementById("admin-users-mgmt-tbody");
            let html = "";
            currentAdminUsers.forEach(u => {
                const statusBadge = u.is_active ? `<span class="text-success">Active</span>` : `<span style="color:#ff3366;">Inactive</span>`;
                const details = `${escapeHtml(u.full_name || 'N/A')}<br><small style="color:var(--text-secondary);">${escapeHtml(u.email || u.username)}</small>`;
                
                html += `<tr>
                    <td>${u.id}</td>
                    <td><strong>${escapeHtml(u.username)}</strong></td>
                    <td>${details}</td>
                    <td>${escapeHtml(u.department)}</td>
                    <td>${formatRole(u.role)}</td>
                    <td><span class="clearance-tag">${u.clearance_level}</span></td>
                    <td>${statusBadge}</td>
                    <td>
                        <button class="btn btn-secondary btn-sm" onclick="openAdminEditModal(${u.id})">Edit User</button>
                        <button class="btn btn-secondary btn-sm btn-danger" onclick="deleteEmployeeUser(${u.id}, '${escapeHtml(u.username)}')">Delete</button>
                    </td>
                </tr>`;
            });
            tbody.innerHTML = html;
        }

    } catch (e) {
        console.error(e);
    }
}

// ADMIN EDIT & DELETE EMPLOYEE ACCOUNT CONTROLLERS
function openAdminEditModal(userId) {
    const userObj = currentAdminUsers.find(u => u.id === userId);
    if (!userObj) return;

    document.getElementById("edit-user-id").value = userObj.id;
    document.getElementById("edit-username").value = userObj.username;
    document.getElementById("edit-fullname").value = userObj.full_name !== "N/A" ? userObj.full_name : "";
    document.getElementById("edit-email").value = userObj.email !== "N/A" ? userObj.email : "";
    document.getElementById("edit-department").value = userObj.department;
    document.getElementById("edit-role").value = userObj.role;
    document.getElementById("edit-clearance").value = userObj.clearance_level;

    document.getElementById("edit-user-modal").classList.remove("hidden");
}

function closeAdminEditModal() {
    document.getElementById("edit-user-modal").classList.add("hidden");
}

async function handleAdminUserSave(event) {
    event.preventDefault();
    const userId = document.getElementById("edit-user-id").value;
    const username = document.getElementById("edit-username").value.trim();
    const fullName = document.getElementById("edit-fullname").value.trim();
    const email = document.getElementById("edit-email").value.trim();
    const dept = document.getElementById("edit-department").value;
    const role = document.getElementById("edit-role").value;
    const clearance = document.getElementById("edit-clearance").value;

    try {
        const response = await fetch(`${API_BASE}/admin/users/${userId}`, {
            method: "PUT",
            headers: {
                "Authorization": `Bearer ${state.token}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                username: username,
                full_name: fullName,
                email: email,
                department: dept,
                role: role,
                clearance_level: clearance
            })
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || "Failed to update employee details.");
        }

        alert("✓ Employee profile and credentials updated successfully.");
        closeAdminEditModal();
        fetchAdminDashboard();
    } catch (e) {
        alert(`Admin Update Error: ${e.message}`);
    }
}

async function deleteEmployeeUser(userId, username) {
    if (!confirm(`Are you sure you want to PERMANENTLY DELETE employee account '${username}'? This operation is restricted to Higher Administration.`)) return;

    try {
        const response = await fetch(`${API_BASE}/admin/users/${userId}`, {
            method: "DELETE",
            headers: { "Authorization": `Bearer ${state.token}` }
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || "Account deletion failed.");
        }

        alert(`✓ Account '${username}' deleted successfully.`);
        fetchAdminDashboard();
    } catch (e) {
        alert(`Deletion Error: ${e.message}`);
    }
}

function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}
