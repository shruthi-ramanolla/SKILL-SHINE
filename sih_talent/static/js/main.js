// static/js/main.js

// Small utility for API requests with token
async function apiFetch(url, options = {}) {
    const token = localStorage.getItem('token');
    options.headers = options.headers || {};
    if (token) {
        options.headers['Authorization'] = token;
    }
    const res = await fetch(url, options);
    return res.json();
}

// Helper to logout
function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('username');
    window.location.href = '/login';
}

// Show user in navbar if logged in
document.addEventListener('DOMContentLoaded', () => {
    const username = localStorage.getItem('username');
    if (username) {
        const nav = document.querySelector('nav .space-x-4');
        if (nav) {
            const span = document.createElement('span');
            span.className = 'text-sm font-medium';
            span.textContent = `👋 ${username}`;
            nav.prepend(span);

            const logoutBtn = document.createElement('button');
            logoutBtn.textContent = 'Logout';
            logoutBtn.className = 'text-sm text-red-600 ml-2';
            logoutBtn.onclick = logout;
            nav.appendChild(logoutBtn);
        }
    }
});
