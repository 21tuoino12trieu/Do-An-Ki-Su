const FASTAPI_SERVER_URL = 'http://localhost:8000'; // Update this to your actual FastAPI server URL
const chatMessages = document.getElementById('chatMessages');
const messageInput = document.getElementById('messageInput');
const sendButton = document.getElementById('sendButton');
const typingIndicator = document.getElementById('typingIndicator');
const typingStatus = document.getElementById('typingStatus');
const userIdInput = document.getElementById('userIdInput');

(function () {
    const originalLog = console.log;
    console.log = function (...args) {
        // Send logs to the server
        fetch('/log', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ logs: args })
        }).catch((err) => originalLog('Failed to send logs:', err));

        // Also log to the browser console
        originalLog.apply(console, args);
    };
})();

// Load saved user ID if exists
if (localStorage.getItem('userId')) {
    userIdInput.value = localStorage.getItem('userId');
}

// Save user ID when changed
userIdInput.addEventListener('change', function() {
    localStorage.setItem('userId', this.value);
});

function getCurrentUserId() {
    return userIdInput.value.trim() || 'default';
}

let isTyping = false;
let typingInterval;
let typingTimeout;

// messageInput.addEventListener('input', function(e) {
//     handleTyping();
// });

messageInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
        console.log("Entering")
        sendMessage();
    }
});

// messageInput.addEventListener('input', function(e) {
//     console.log(e.inputType)
    
//     if (e.inputType === 'insertLineBreak' || e.target.value.includes('\n')) {
//         console.log("Entering")
//         sendMessage();
//     }
//     else{
//         handleTyping();
//     }
// });

async function handleTyping() {
    if (!isTyping) {
        isTyping = true;

        // Start sending typing status every 1 second (1000ms)
        typingInterval = setInterval(async () => {
            const userId = getCurrentUserId();
            console.log(`User ${userId} is typing...`);  // This will show in Docker logs
            
            try {
                await fetch(`${FASTAPI_SERVER_URL}/typing?user_id=${userId}`, {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                });
            } catch (error) {
                console.error('Error sending typing status:', error);
            }
        }, 1000);

        // Send the first typing status immediately
        const userId = getCurrentUserId();
        console.log(`User ${userId} is typing...`);  // This will show in Docker logs
        try {
            await fetch(`${FASTAPI_SERVER_URL}/typing?user_id=${userId}`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                }
            });
        } catch (error) {
            console.error('Error sending typing status:', error);
        }
    }

    // Reset inactivity timeout to stop the typing after 2 seconds of inactivity
    clearTimeout(typingTimeout);
    typingTimeout = setTimeout(() => {
        stopTyping();
    }, 1000);  // Stop typing status after 2 seconds of inactivity
}

async function stopTyping() {
    clearInterval(typingInterval);
    isTyping = false;

    const userId = getCurrentUserId();
    console.log(`User ${userId} stopped typing`);  // This will show in Docker logs
}




function addMessage(content, isUser) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isUser ? 'user-message' : 'bot-message'}`;
    messageDiv.textContent = content;
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function sendMessage() {
    const message = messageInput.value.trim();
    if (!message) return;

    // messageInput.disabled = true;
    // sendButton.disabled = true;

    const userId = getCurrentUserId();
    addMessage(message, true);
    messageInput.value = '';
    

    try {
        const response = await fetch(`${FASTAPI_SERVER_URL}/chat2`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'include', // Add this
            body: JSON.stringify({

                query: message,
                user_id: userId
            })
        });
        if (response.ok) {            
            const contentType = response.headers.get('Content-Type');

            console.log(response)
            console.log(contentType)
            if (contentType && contentType.includes('application/json')) {
                // Handle Dictionary response
                const data = await response.json();
                console.log("1")
                console.log(data)
                if (data.hasOwnProperty("message")) {
                    addMessage(data.message);
                }
            }  else if (contentType && contentType.includes('text')) {
                
                const reader = response.body.getReader();
                const decoder = new TextDecoder();

                while (true) {
                    const {value, done} = await reader.read();

                    if (done) break;
                    
                    const text = decoder.decode(value);
                    console.log("text:")
                    console.log(text)
                    
                    if (text.startsWith('data:')) {
                        const content = text.slice(5).trim();
                        if (content) {
                            if (content=="skip"){
                                break
                            }
                            addMessage(content, false);
                        }
                    }
                    
                }
            }
        } else {
            addMessage('Sorry, I encountered an error. Please try again.', false);
        }
    } catch (error) {
        console.error('Error:', error);
        addMessage('Sorry, I encountered an error. Please try again.', false);
    } finally {
        messageInput.disabled = false;
        sendButton.disabled = false;
        // typingIndicator.style.display = 'none';
        messageInput.focus();
    }
}

async function addNewUser() {
    const userId = getCurrentUserId();

    try {
        const response = await fetch(`${FASTAPI_SERVER_URL}/new_user`, 
            {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    user_id: userId
                })
            }
        );
        const data = await response.json();
        addMessage(`New user created: ${JSON.stringify(data)}`, false);
    } catch (error) {
        console.error('Error:', error);
        addMessage('Error creating new user', false);
    }
}

async function chatHistories() {
    try {
        const userId = getCurrentUserId();
        const response = await fetch(`${FASTAPI_SERVER_URL}/chatHistory?user_id=${userId}`);
        if (response.ok) {
            const data = await response.json();
            chatMessages.innerHTML = ''; // Clear existing messages
            
            // Add each message from history
            data.forEach(msg => {
                const isUser = msg.role === 'user';
                addMessage(msg.content, isUser);
            });
        }
    } catch (error) {
        console.error('Error fetching chat history:', error);
        addMessage('Error loading chat history', false);
    }
}

async function listUsers() {
    try {
        const response = await fetch(`${FASTAPI_SERVER_URL}/list_all_users`);
        const data = await response.json();
        const usersList = document.getElementById('usersList');
        usersList.innerHTML = '<h3>Users:</h3>' + 
            data.map(user => `<div>${JSON.stringify(user)}</div>`).join('');
    } catch (error) {
        console.error('Error:', error);
        addMessage('Error listing users', false);
    }
}

async function clearChat() {
    try {
        const response = await fetch(`${FASTAPI_SERVER_URL}/clear`);
        if (response.ok) {
            chatMessages.innerHTML = '';
            addMessage('Chat history cleared', false);
        }
    } catch (error) {
        console.error('Error:', error);
        addMessage('Error clearing chat history', false);
    }
}

async function clearUser() {
    try {
        const userId = getCurrentUserId();
        const response = await fetch(`${FASTAPI_SERVER_URL}/clear_user`,
            {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    user_id: userId
                })
            }
        );
        if (response.ok) {
            chatMessages.innerHTML = '';
            addMessage('User cleared', false);
        }
    } catch (error) {
        addMessage('Error clearing user', false);
    }
}

// const evtSource = new EventSource(`${FASTAPI_SERVER_URL}/typing-updates`);

// evtSource.onmessage = function(event) {
//     const data = JSON.parse(event.data);
//     const currentUserId = getCurrentUserId();
//     if (data.telegram_id !== currentUserId) {
//         typingStatus.textContent = data.status === 'typing' 
//             ? `${data.telegram_id} is typing...` 
//             : '';
//     }
// };

// evtSource.onerror = function(err) {
//     console.error("EventSource failed:", err);
// };

// window.addEventListener('beforeunload', () => {
//     evtSource.close();
// });


function fetchMemory() {
    const userId = getCurrentUserId();
    console.log("Fetch memory: " + userId);
  
    fetch(`${FASTAPI_SERVER_URL}/memory?user_id=${userId}`)
      .then(response => response.json())
      .then(data => {
        const memoryBox = document.getElementById('memoryBox');
        
        // Parse the string if it's a JSON string
        const jsonData = typeof data === 'string' ? JSON.parse(data) : data;
        
        // Format with proper indentation
        const formattedJson = JSON.stringify(jsonData, null, 4);
        
        memoryBox.innerHTML = `<pre style="
          background-color: #f5f5f5;
          padding: 1rem;
          border-radius: 4px;
          font-family: monospace;
          white-space: pre-wrap;
          word-wrap: break-word;
          overflow-wrap: break-word;
        ">${formattedJson}</pre>`;
      })
      .catch(error => {
        console.error('Error fetching memory:', error);
        const memoryBox = document.getElementById('memoryBox');
        memoryBox.innerHTML = `
          <div style="color: red; padding: 1rem;">
            Error fetching memory: ${error.message}
          </div>
        `;
      });
  }

setInterval(fetchMemory, 5000);
fetchMemory(); // Gọi ngay khi tải trang

