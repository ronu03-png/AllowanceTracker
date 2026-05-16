const authScreen = document.getElementById("auth-screen");
const trackerScreen = document.getElementById("tracker-screen");
const loginForm = document.getElementById("login-form");
const signupForm = document.getElementById("signup-form");
const showLoginBtn = document.getElementById("show-login");
const showSignupBtn = document.getElementById("show-signup");
const gotoSignupBtn = document.getElementById("goto-signup");
const gotoLoginBtn = document.getElementById("goto-login");
const logoutButton = document.getElementById("logout-button");
const userNameEl = document.getElementById("user-name");
const entryForm = document.getElementById("entry-form");
const historyList = document.getElementById("history-list");
const entryCount = document.getElementById("entry-count");
const summaryTotal = document.getElementById("summary-total");
const summarySpent = document.getElementById("summary-spent");
const summaryRemaining = document.getElementById("summary-remaining");

const STORAGE_KEY = "allowance-tracker-users";
const SESSION_KEY = "allowance-tracker-session";

const state = {
  currentUser: null,
  users: loadUsers(),
};

function loadUsers() {
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored ? JSON.parse(stored) : {};
}

function saveUsers() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state.users));
}

function setSession(email) {
  localStorage.setItem(SESSION_KEY, email);
}

function clearSession() {
  localStorage.removeItem(SESSION_KEY);
}

function getSession() {
  return localStorage.getItem(SESSION_KEY);
}

function showLogin() {
  showLoginBtn.classList.add("active");
  showSignupBtn.classList.remove("active");
  loginForm.classList.remove("hidden");
  signupForm.classList.add("hidden");
}

function showSignup() {
  showSignupBtn.classList.add("active");
  showLoginBtn.classList.remove("active");
  signupForm.classList.remove("hidden");
  loginForm.classList.add("hidden");
}

function loadUserData(email) {
  const user = state.users[email];
  if (!user) return null;
  return {
    ...user,
    entries: user.entries || [],
    allowance: typeof user.allowance === "number" ? user.allowance : 0,
  };
}

function updateUserDisplay() {
  const user = loadUserData(state.currentUser);
  if (!user) return;

  userNameEl.textContent = user.name;
  const spent = user.entries.reduce((sum, entry) => sum + entry.amount, 0);
  const remaining = user.allowance - spent;

  summaryTotal.textContent = `₱${user.allowance.toFixed(2)}`;
  summarySpent.textContent = `₱${spent.toFixed(2)}`;
  summaryRemaining.textContent = `₱${remaining.toFixed(2)}`;
  entryCount.textContent = `${user.entries.length} ${user.entries.length === 1 ? "entry" : "entries"}`;

  if (user.entries.length === 0) {
    historyList.innerHTML =
      '<p class="empty-state">No allowance logs yet. Add your first spending entry.</p>';
    return;
  }

  const sorted = [...user.entries].sort(
    (a, b) => new Date(b.date) - new Date(a.date),
  );
  historyList.innerHTML = sorted
    .map((entry) => {
      const date = new Date(entry.date).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
      return `
        <div class="entry-card">
          <div class="entry-top">
            <strong>$${entry.amount.toFixed(2)}</strong>
            <span>${entry.category}</span>
          </div>
          <div class="entry-meta">
            <span>${date}</span>
            <span>${entry.location}</span>
          </div>
          <p class="entry-description">${entry.description || "No description provided."}</p>
        </div>
      `;
    })
    .join("");
}

function showTracker() {
  authScreen.classList.add("hidden");
  trackerScreen.classList.remove("hidden");
  updateUserDisplay();
}

function showAuth() {
  trackerScreen.classList.add("hidden");
  authScreen.classList.remove("hidden");
}

function handleLogin(event) {
  event.preventDefault();
  const email = document
    .getElementById("login-email")
    .value.trim()
    .toLowerCase();
  const password = document.getElementById("login-password").value;
  const user = state.users[email];

  if (!user || user.password !== password) {
    alert("Incorrect email or password. Please try again.");
    return;
  }

  state.currentUser = email;
  setSession(email);
  showTracker();
  loginForm.reset();
}

function handleSignup(event) {
  event.preventDefault();
  const name = document.getElementById("signup-name").value.trim();
  const email = document
    .getElementById("signup-email")
    .value.trim()
    .toLowerCase();
  const password = document.getElementById("signup-password").value;

  if (!name || !email || !password) {
    alert("Please fill in all fields.");
    return;
  }

  if (state.users[email]) {
    alert("An account already exists with that email.");
    return;
  }

  state.users[email] = {
    name,
    email,
    password,
    allowance: 50,
    entries: [],
  };
  saveUsers();

  state.currentUser = email;
  setSession(email);
  showTracker();
  signupForm.reset();
}

function handleEntrySubmit(event) {
  event.preventDefault();

  const amount = parseFloat(document.getElementById("entry-amount").value);
  const category = document.getElementById("entry-category").value;
  const location = document.getElementById("entry-location").value.trim();
  const date = document.getElementById("entry-date").value;
  const description = document.getElementById("entry-description").value.trim();

  if (!amount || !category || !location || !date) {
    alert("Please complete every required field.");
    return;
  }

  const user = loadUserData(state.currentUser);
  if (!user) return;

  const entry = {
    id: Date.now().toString(),
    amount,
    category,
    location,
    date,
    description,
  };

  state.users[state.currentUser].entries.push(entry);
  saveUsers();
  updateUserDisplay();
  entryForm.reset();
}

function handleLogout() {
  clearSession();
  state.currentUser = null;
  showAuth();
}

function initialize() {
  const sessionEmail = getSession();
  if (sessionEmail && state.users[sessionEmail]) {
    state.currentUser = sessionEmail;
    showTracker();
    return;
  }
  showAuth();
}

showLoginBtn.addEventListener("click", showLogin);
showSignupBtn.addEventListener("click", showSignup);
gotoSignupBtn.addEventListener("click", showSignup);
gotoLoginBtn.addEventListener("click", showLogin);
loginForm.addEventListener("submit", handleLogin);
signupForm.addEventListener("submit", handleSignup);
entryForm.addEventListener("submit", handleEntrySubmit);
logoutButton.addEventListener("click", handleLogout);

initialize();
