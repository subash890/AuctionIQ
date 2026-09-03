// === AUTH UTILITIES ===
function getCurrentUser() {
    const user = localStorage.getItem('bidmind_user');
    return user ? JSON.parse(user) : null;
}

function requireAuth() {
    const user = getCurrentUser();
    if(!user || !user.logged_in) {
        location.href = '/';
        return null;
    }
    return user;
}

function logout() {
    localStorage.removeItem('bidmind_user');
    location.href = '/';
}

function formatCurrency(amount) {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount);
}

function formatTime(seconds) {
    if(seconds < 0) return "Ended";
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    return `${h.toString().padStart(2,'0')}:${m.toString().padStart(2,'0')}:${s.toString().padStart(2,'0')}`;
}

// === NOTIFICATION SYSTEM ===
function showNotification(message, type = 'info', duration = 3000) {
    // Create notification element
    const notif = document.createElement('div');
    notif.className = `notification ${type}`;
    notif.innerHTML = `
        <span>${message}</span>
        <button onclick="this.parentElement.remove()">×</button>
    `;
    
    // Add to page
    let container = document.getElementById('notification-container');
    if(!container) {
        container = document.createElement('div');
        container.id = 'notification-container';
        document.body.appendChild(container);
    }
    container.appendChild(notif);
    
    // Auto-remove
    if(duration > 0) {
        setTimeout(() => notif.remove(), duration);
    }
}

// === WEBSOCKET HELPER ===
function connectWebSocket(auctionId, callbacks = {}) {
    const ws = new WebSocket(`ws://${location.host}/ws/bid/${auctionId}`);
    
    ws.onopen = () => {
        console.log('✅ WebSocket connected');
        if(callbacks.onOpen) callbacks.onOpen();
    };
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if(callbacks.onMessage) callbacks.onMessage(data);
    };
    
    ws.onclose = () => {
        console.log('🔌 WebSocket disconnected');
        if(callbacks.onClose) callbacks.onClose();
        // Auto-reconnect after 3 seconds
        setTimeout(() => connectWebSocket(auctionId, callbacks), 3000);
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        if(callbacks.onError) callbacks.onError(error);
    };
    
    return ws;
}

// === PAGE-SPECIFIC: Dashboard ===
async function loadAuctions(containerId = 'auctionList') {
    const container = document.getElementById(containerId);
    if(!container) return;
    
    container.innerHTML = '<p>Loading auctions...</p>';
    
    try {
        const res = await fetch('/api/auctions?active_only=true');
        const auctions = await res.json();
        
        if(auctions.length === 0) {
            container.innerHTML = '<p>No active auctions. <a href="/create">Create one!</a></p>';
            return;
        }
        
        container.innerHTML = auctions.map(a => `
            <div class="card auction-card">
                <h3>${a.title}</h3>
                <p style="color:#666; margin:0.5rem 0;">${a.description.substring(0, 100)}${a.description.length > 100 ? '...' : ''}</p>
                <div class="auction-meta">
                    <span class="price">${formatCurrency(a.current_bid)}</span>
                    <span class="ai-badge">🤖 AI: ${formatCurrency(a.ai_prediction || 0)}</span>
                </div>
                <div class="auction-actions">
                    <button class="btn-primary" onclick="location.href='/auction/${a.id}'">View & Bid</button>
                    <button class="btn-secondary" onclick="getRecommendation(${a.id})">💡 Get Recommendation</button>
                </div>
            </div>
        `).join('');
        
    } catch(err) {
        container.innerHTML = `<p class="error">❌ Failed to load auctions: ${err.message}</p>`;
    }
}

async function getRecommendation(auctionId) {
    const user = getCurrentUser();
    if(!user) {
        showNotification('Please login first', 'error');
        return;
    }
    
    try {
        const res = await fetch(`/api/auctions/${auctionId}/recommendation?user_id=${user.user_id}`);
        const rec = await res.json();
        
        showNotification(
            `💡 Recommended: ${formatCurrency(rec.recommended_bid)} (${rec.strategy})`,
            'info',
            5000
        );
    } catch(err) {
        showNotification('Failed to get recommendation', 'error');
    }
}

// === PAGE-SPECIFIC: Analytics ===
async function loadAnalytics() {
    try {
        const res = await fetch('/api/analytics/dashboard');
        const data = await res.json();
        
        // Update stat cards
        const stats = {
            totalAuctions: data.overview.total_auctions,
            activeAuctions: data.overview.active_auctions,
            totalBids: data.overview.total_bids,
            totalRevenue: formatCurrency(data.overview.total_revenue)
        };
        
        Object.entries(stats).forEach(([id, value]) => {
            const el = document.getElementById(id);
            if(el) el.textContent = value;
        });
        
        // Render recent activity
        const activityDiv = document.getElementById('recentActivity');
        if(activityDiv && data.recent_activity?.length) {
            activityDiv.innerHTML = data.recent_activity.map(bid => `
                <div class="log-entry">
                    <span>User #${bid.user_id}</span>
                    <span>${formatCurrency(bid.amount)}</span>
                    <span>${new Date(bid.timestamp).toLocaleTimeString()}</span>
                </div>
            `).join('');
        }
        
        // Initialize charts if Chart.js is loaded
        if(typeof Chart !== 'undefined') {
            initCharts(data);
        }
        
    } catch(err) {
        console.error('Failed to load analytics:', err);
        showNotification('Failed to load analytics', 'error');
    }
}

function initCharts(data) {
    // Top Bidders Chart
    const ctx = document.getElementById('topBiddersChart');
    if(ctx && data.top_bidders?.length) {
        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.top_bidders.map(b => b.username),
                datasets: [{
                    label: 'Total Spent',
                    data: data.top_bidders.map(b => b.total_spent),
                    backgroundColor: '#6f42c1',
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } }
            }
        });
    }
}

// === PAGE-SPECIFIC: Chat ===
async function loadChatHistory() {
    const user = getCurrentUser();
    if(!user) return;
    
    try {
        const res = await fetch(`/api/chat/history?user_id=${user.user_id}`);
        const messages = await res.json();
        
        const container = document.getElementById('chatMessages');
        if(!container) return;
        
        if(messages.length === 0) {
            container.innerHTML = '<div class="chat-empty">Start a conversation with AI! 💬</div>';
            return;
        }
        
        container.innerHTML = messages.map(m => `
            <div class="chat-message user">
                <strong>You:</strong> ${m.message}
            </div>
            <div class="chat-message ai">
                <strong>🤖 AI:</strong> ${m.response}
            </div>
        `).join('');
        
        container.scrollTop = container.scrollHeight;
        
    } catch(err) {
        console.error('Failed to load chat:', err);
    }
}

async function sendChatMessage(message) {
    const user = getCurrentUser();
    if(!user) {
        showNotification('Please login first', 'error');
        return;
    }
    
    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({message, user_id: user.user_id})
        });
        
        const data = await res.json();
        loadChatHistory(); // Reload to show new message
        
        return data;
    } catch(err) {
        showNotification('Failed to send message', 'error');
        throw err;
    }
}

// === PAGE-SPECIFIC: Auto-Bot ===
async function loadBots() {
    const user = getCurrentUser();
    if(!user) return;
    
    try {
        const res = await fetch(`/api/bot/status/${user.user_id}`);
        const data = await res.json();
        
        const container = document.getElementById('botList');
        if(!container) return;
        
        if(!data.bots?.length) {
            container.innerHTML = '<p>No active bots. Create one below! 🤖</p>';
            return;
        }
        
        container.innerHTML = data.bots.map(bot => `
            <div class="card bot-card">
                <h4>Auction #${bot.config.auction_id}</h4>
                <p><strong>Strategy:</strong> ${bot.config.strategy}</p>
                <p><strong>Max Bid:</strong> ${formatCurrency(bot.config.max_bid)}</p>
                <p><strong>Last Bid:</strong> ${bot.last_bid ? formatCurrency(bot.last_bid) : 'None'}</p>
                <span class="badge ${bot.config.is_active ? 'success' : 'inactive'}">
                    ${bot.config.is_active ? '🟢 Active' : '⚪ Inactive'}
                </span>
            </div>
        `).join('');
        
    } catch(err) {
        console.error('Failed to load bots:', err);
    }
}

async function createBot(config) {
    const user = getCurrentUser();
    if(!user) {
        showNotification('Please login first', 'error');
        return;
    }
    
    try {
        const res = await fetch('/api/bot/create', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({...config, user_id: user.user_id})
        });
        
        const data = await res.json();
        
        if(res.ok) {
            showNotification(data.message || 'Bot created!', 'success');
            loadBots(); // Refresh list
        } else {
            showNotification(data.detail || 'Failed to create bot', 'error');
        }
        
        return data;
    } catch(err) {
        showNotification('Network error', 'error');
        throw err;
    }
}