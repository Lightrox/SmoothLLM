// Global variables
let currentUser = null;
let promptHistory = [];

// DOM elements
const smoothllmForm = document.getElementById('smoothllmForm');
const submitBtn = document.getElementById('submitBtn');
const resultsSection = document.getElementById('resultsSection');
const loadingSpinner = document.getElementById('loadingSpinner');
const signInBtn = document.getElementById('signInBtn');
const signInModal = document.getElementById('signInModal');
const signUpModal = document.getElementById('signUpModal');
const historyModal = document.getElementById('historyModal');
const confirmModal = document.getElementById('confirmModal');
const confirmOkBtn = document.getElementById('confirmOk');
const confirmCancelBtn = document.getElementById('confirmCancel');
const confirmMessage = document.getElementById('confirmMessage');
const perturbationPct = document.getElementById('perturbationPct');
const perturbationValue = document.getElementById('perturbationValue');

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
    setupEventListeners();
    initBackendOrigin();
});

function initializeApp() {
    // Update perturbation percentage display
    updatePerturbationDisplay();
    
    // Check if user is logged in via server session
    checkUserSession();
}

function setupEventListeners() {
    // Form submission
    smoothllmForm.addEventListener('submit', handleFormSubmit);
    
    // Perturbation range slider
    perturbationPct.addEventListener('input', updatePerturbationDisplay);
    
    // Modal controls: do not intercept sign-in link; let it navigate to /signin
    
    // Close modals when clicking outside
    window.addEventListener('click', function(event) {
        if (event.target.classList.contains('modal')) {
            closeModal(event.target.id);
        }
    });
    
    // Close buttons
    document.querySelectorAll('.close').forEach(closeBtn => {
        closeBtn.addEventListener('click', function() {
            const modal = this.closest('.modal');
            closeModal(modal.id);
        });
    });

    // Confirm dialog controls
    if (confirmCancelBtn) confirmCancelBtn.addEventListener('click', () => closeModal('confirmModal'));
    const closeConfirm = document.querySelector('[data-close-confirm]');
    if (closeConfirm) closeConfirm.addEventListener('click', () => closeModal('confirmModal'));
    
    // Sign in form
    document.getElementById('signInForm').addEventListener('submit', handleSignIn);
    
    // Sign up form
    document.getElementById('signUpForm').addEventListener('submit', handleSignUp);
    
    // Modal navigation
    document.getElementById('signUpLink').addEventListener('click', function(e) {
        e.preventDefault();
        closeModal('signInModal');
        openModal('signUpModal');
    });
    
    document.getElementById('signInLink').addEventListener('click', function(e) {
        e.preventDefault();
        closeModal('signUpModal');
        openModal('signInModal');
    });
}

// Configure backend origin for multi-origin deployments (e.g., Vercel frontend + Flask backend)
function initBackendOrigin() {
    try {
        // Allow setting via localStorage to avoid hardcoding
        // Example: localStorage.setItem('backend_origin', 'https://your-backend.example.com')
        window.__backendOrigin = localStorage.getItem('backend_origin') || '';
    } catch (e) {
        window.__backendOrigin = '';
    }
}

function buildBackendUrl(path) {
    try {
        const origin = window.__backendOrigin || '';
        if (!origin) return path;
        return origin.replace(/\/$/, '') + path;
    } catch (_) {
        return path;
    }
}

function updatePerturbationDisplay() {
    perturbationValue.textContent = perturbationPct.value + '%';
}

function handleFormSubmit(e) {
    e.preventDefault();
    
    const formData = new FormData(smoothllmForm);
    const prompt = formData.get('prompt').trim();
    const perturbations = formData.get('perturbations');
    const perturbationType = formData.get('perturbationType');
    const perturbationPct = formData.get('perturbationPct');
    
    if (!prompt) {
        alert('Please enter a prompt to analyze.');
        return;
    }
    
    // Show loading spinner
    showLoading();
    
    // Prepare request data
    const requestData = {
        prompt: prompt,
        smoothllm_num_copies: parseInt(perturbations),
        smoothllm_pert_type: perturbationType,
        smoothllm_pert_pct: parseInt(perturbationPct),
        target_model: 'tinyllama' // Default model
    };
    
    // Make API call
    fetch('/api/analyze', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(requestData)
    })
    .then(response => {
        console.log('Response status:', response.status);
        console.log('Response headers:', response.headers);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        return response.json();
    })
    .then(data => {
        console.log('Response data:', data);
        hideLoading();
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        displayResults(data, requestData);
        
        // Show mock response message if applicable
        if (data.mock_response) {
            const resultCard = document.querySelector('.result-card');
            if (resultCard && data.message) {
                const messageDiv = document.createElement('div');
                messageDiv.className = 'mock-message';
                messageDiv.style.cssText = 'background: #fef3c7; color: #92400e; padding: 0.75rem; border-radius: 8px; margin-top: 1rem; font-size: 0.9rem;';
                messageDiv.innerHTML = `<i class="fas fa-info-circle"></i> ${data.message}`;
                resultCard.appendChild(messageDiv);
            }
        }
        
        // Save to history if user is logged in
        if (currentUser) {
            saveToHistory(prompt, data, requestData);
        }
    })
    .catch(error => {
        hideLoading();
        console.error('Error:', error);
        
        // Show more specific error message
        let errorMessage = 'An error occurred while analyzing the prompt. Please try again.';
        
        if (error.message) {
            errorMessage += `\n\nError details: ${error.message}`;
        }
        
        // Check if it's a network error
        if (error.name === 'TypeError' && error.message.includes('fetch')) {
            errorMessage = 'Network error: Could not connect to the server. Make sure the Flask app is running.';
        }
        
        alert(errorMessage);
    });
}

function showLoading() {
    loadingSpinner.style.display = 'block';
    resultsSection.style.display = 'none';
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Analyzing...';
}

function hideLoading() {
    loadingSpinner.style.display = 'none';
    submitBtn.disabled = false;
    submitBtn.innerHTML = '<i class="fas fa-shield-check"></i> Analyze Safety';
}

function displayResults(data, requestData) {
    const resultStatus = document.getElementById('resultStatus');
    const jailbreakRate = document.getElementById('jailbreakRate');
    const perturbationsUsed = document.getElementById('perturbationsUsed');
    const perturbationTypeUsed = document.getElementById('perturbationTypeUsed');
    
    // Determine if the prompt is safe or unsafe
    const isSafe = data.jb_percentage < 50; // Less than 50% jailbreak rate is considered safe
    
    // Update status display
    resultStatus.textContent = isSafe ? 'SAFE' : 'UNSAFE';
    resultStatus.className = `result-status ${isSafe ? 'safe' : 'unsafe'}`;
    
    // Update result details
    jailbreakRate.textContent = `${data.jb_percentage.toFixed(2)}%`;
    perturbationsUsed.textContent = requestData.smoothllm_num_copies;
    perturbationTypeUsed.textContent = requestData.smoothllm_pert_type.replace('Perturbation', '');
    
    // Show results section
    resultsSection.style.display = 'block';
    resultsSection.scrollIntoView({ behavior: 'smooth' });
}

function saveToHistory(prompt, result, requestData) {
    const historyItem = {
        id: Date.now(),
        prompt: prompt,
        timestamp: new Date().toISOString(),
        isSafe: result.jb_percentage < 50,
        jailbreakRate: result.jb_percentage,
        perturbations: requestData.smoothllm_num_copies,
        perturbationType: requestData.smoothllm_pert_type,
        perturbationPct: requestData.smoothllm_pert_pct
    };
    
    promptHistory.unshift(historyItem);
    
    // Keep only last 50 items
    if (promptHistory.length > 50) {
        promptHistory = promptHistory.slice(0, 50);
    }
    
    // History is automatically saved to server via the /api/analyze endpoint
}

function checkUserSession() {
    // Check if user is logged in via server session
    fetch('/api/user', { credentials: 'include' })
        .then(res => res.ok ? res.json() : null)
        .then(data => {
            if (data && data.user) {
                currentUser = data.user;
                loadPromptHistory();
                updateUIForLoggedInUser();
            }
        })
        .catch(() => {
            // User not authenticated, stay on current page
            console.log('User not authenticated');
        });
}

function loadPromptHistory() {
    if (currentUser) {
        // Load from server
        fetch('/api/history', { credentials: 'include' })
        .then(response => response.json())
        .then(data => {
            if (data.history) {
                promptHistory = data.history;
            }
        })
        .catch(error => {
            console.error('Error loading history from server:', error);
        });
    }
}

function updateUIForLoggedInUser() {
    if (currentUser) {
        // Clear any existing dynamic buttons
        const navActions = document.querySelector('.nav-actions');
        if (!navActions) return;

        // Reset primary button to Profile
        signInBtn.classList.remove('btn-signin');
        signInBtn.classList.add('btn-nav-secondary');
        signInBtn.innerHTML = `<i class="fas fa-user"></i> Profile: ${currentUser.name}`;
        signInBtn.href = buildBackendUrl('/profile');
        signInBtn.onclick = null;
        
        // Add history button to navbar
        if (!document.getElementById('historyBtn')) {
            const historyBtn = document.createElement('a');
            historyBtn.id = 'historyBtn';
            historyBtn.className = 'btn-nav-secondary';
            historyBtn.innerHTML = '<i class="fas fa-history"></i> History';
            historyBtn.href = '#';
            historyBtn.onclick = (e) => {
                e.preventDefault();
                openModal('historyModal');
            };
            
            navActions.insertBefore(historyBtn, signInBtn);
        }
        
        // Add sign out button
        if (!document.getElementById('signOutBtn')) {
            const signOutBtn = document.createElement('a');
            signOutBtn.id = 'signOutBtn';
            signOutBtn.className = 'btn-nav-secondary';
            signOutBtn.innerHTML = '<i class="fas fa-sign-out-alt"></i> Sign Out';
            signOutBtn.href = '#';
            signOutBtn.onclick = (e) => {
                e.preventDefault();
                handleSignOut();
            };
            
            navActions.insertBefore(signOutBtn, signInBtn);
        }
    }
}

function openModal(modalId) {
    const modal = document.getElementById(modalId);
    modal.style.display = 'block';
    document.body.style.overflow = 'hidden';
    
    if (modalId === 'historyModal') {
        displayPromptHistory();
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    modal.style.display = 'none';
    document.body.style.overflow = 'auto';
}

function displayPromptHistory() {
    const historyContent = document.getElementById('historyContent');
    
    if (promptHistory.length === 0) {
        historyContent.innerHTML = '<p style="text-align: center; color: #6b7280; padding: 2rem;">No prompt history found.</p>';
        return;
    }
    
    historyContent.innerHTML = promptHistory.map(item => `
        <div class="history-item">
            <div class="history-prompt">${item.prompt}</div>
            <div class="history-meta">
                <span>${new Date(item.timestamp).toLocaleString()}</span>
                <span class="history-status ${item.isSafe ? 'safe' : 'unsafe'}">
                    ${item.isSafe ? 'Safe' : 'Unsafe'}
                </span>
            </div>
        </div>
    `).join('');
}

function handleSignIn(e) {
    e.preventDefault();
    
    const formData = new FormData(e.target);
    const email = formData.get('email');
    const password = formData.get('password');
    
    if (!email || !password) {
        alert('Please enter both email and password.');
        return;
    }
    
    // Make API call to backend
    fetch('/api/signin', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({ email, password })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            currentUser = data.user;
            loadPromptHistory();
            updateUIForLoggedInUser();
            closeModal('signInModal');
            e.target.reset();
            alert('Successfully signed in!');
        } else {
            alert(data.error || 'Sign in failed');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('An error occurred during sign in');
    });
}

function handleSignUp(e) {
    e.preventDefault();
    
    const formData = new FormData(e.target);
    const name = formData.get('name');
    const email = formData.get('email');
    const password = formData.get('password');
    
    if (!name || !email || !password) {
        alert('Please fill in all fields.');
        return;
    }
    
    if (password.length < 6) {
        alert('Password must be at least 6 characters long.');
        return;
    }
    
    // Make API call to backend
    fetch('/api/signup', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({ name, email, password })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            currentUser = data.user;
            loadPromptHistory();
            updateUIForLoggedInUser();
            closeModal('signUpModal');
            e.target.reset();
            alert('Successfully signed up!');
        } else {
            alert(data.error || 'Sign up failed');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('An error occurred during sign up');
    });
}

function handleSignOut() {
    // Show custom confirm modal
    if (!confirmModal) return;
    confirmMessage.textContent = 'Are you sure you want to sign out?';
    openModal('confirmModal');
    
    const onConfirm = () => {
        fetch('/api/signout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Clear user data
                currentUser = null;
                promptHistory = [];
                
                // Reset UI
                signInBtn.innerHTML = '<i class="fas fa-user"></i> Sign In';
                signInBtn.href = '/signin';
                signInBtn.onclick = null;
                
                // Remove additional buttons
                const historyBtn = document.getElementById('historyBtn');
                const signOutBtn = document.getElementById('signOutBtn');
                if (historyBtn) historyBtn.remove();
                if (signOutBtn) signOutBtn.remove();
                
                closeModal('confirmModal');
                // Redirect to home
                window.location.href = '/';
            }
        })
        .catch(error => {
            console.error('Error signing out:', error);
            closeModal('confirmModal');
        })
        .finally(() => {
            confirmOkBtn.removeEventListener('click', onConfirm);
        });
    };
    
    if (confirmOkBtn) {
        confirmOkBtn.addEventListener('click', onConfirm);
    }
}

// Utility function to format perturbation type names
function formatPerturbationType(type) {
    return type.replace('Perturbation', '').replace(/([A-Z])/g, ' $1').trim();
}

// Add smooth scrolling for better UX
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});

// Add keyboard shortcuts
document.addEventListener('keydown', function(e) {
    // Escape key to close modals
    if (e.key === 'Escape') {
        const openModal = document.querySelector('.modal[style*="block"]');
        if (openModal) {
            closeModal(openModal.id);
        }
    }
    
    // Ctrl+Enter to submit form
    if (e.ctrlKey && e.key === 'Enter') {
        if (smoothllmForm.checkValidity()) {
            handleFormSubmit(new Event('submit'));
        }
    }
});
