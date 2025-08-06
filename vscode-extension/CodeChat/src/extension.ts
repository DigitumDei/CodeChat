import * as vscode from 'vscode';
import axios from 'axios';

let statusBarItem: vscode.StatusBarItem;
let healthInterval: NodeJS.Timeout;

export function activate(context: vscode.ExtensionContext) { 

  // 1 create a status bar entry
  statusBarItem = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Right, 
    /* priority */ 100
  );
  statusBarItem.command = 'codechat.openSettings';
  context.subscriptions.push(statusBarItem);

  // helper to do one health‐ping + status‐bar refresh
  async function refreshHealth() {
    const cfg = vscode.workspace.getConfiguration('codechat');
    const daemonUrl = cfg.get<string>('daemonUrl')!;
    let healthy = false;
    try {
      const res = await fetch(`${daemonUrl}/health`);
      healthy = res.ok;
    } catch {
      healthy = false;
    }
    const now = new Date();
    // update icon + color
    if (healthy) {
      statusBarItem.text = '✔ CodeChat';
      statusBarItem.color = 'lightgreen';
    } else {
      statusBarItem.text = '✖ CodeChat';
      statusBarItem.color = 'red';
    }
    // show last‐ping in tooltip
    statusBarItem.tooltip = `Last ping: ${now.toLocaleString()}`;
    statusBarItem.show();
  }

  // run immediately, then every 30s
  refreshHealth();
  healthInterval = setInterval(refreshHealth, 30_000);
  context.subscriptions.push({ dispose: () => clearInterval(healthInterval) });

  // 4) your existing helloWorld command
  const disposable = vscode.commands.registerCommand(
    'codechat.helloWorld',
    () => vscode.window.showInformationMessage('CodeChat extension wired up!'));
  context.subscriptions.push(disposable);

		// 5) register “open settings” command
  const openSettings = vscode.commands.registerCommand(
    'codechat.openSettings',  
    () => {
    // this will open the Settings UI filtered to your daemonUrl setting
    vscode.commands.executeCommand(
    'workbench.action.openSettings',
    'codechat.daemonUrl'
    ); 
  });
  context.subscriptions.push(openSettings);

  console.log('🔌 CodeChat extension activated');
  
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(
      'codechat.chat',
      new ChatViewProvider(context),
      {
        // so that your React/vanilla bundle survives when hidden
        webviewOptions: { retainContextWhenHidden: true }
      }
    )
  );
}

class ChatViewProvider implements vscode.WebviewViewProvider {
  constructor(private ctx: vscode.ExtensionContext) {}

  public resolveWebviewView(
    view: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext
  ) {
    view.webview.options = {
      enableScripts: true
    };

    // Load history from workspaceState (or default empty)
    const history = this.ctx.workspaceState.get<ChatMessage[]>(
      'chatHistory',
      []
    );

    view.webview.html = this.getHtmlForWebview(view.webview, history);

    // Listen for messages from the webview
    view.webview.onDidReceiveMessage(async msg => {
      switch (msg.command) {
        case 'send':
          await this.postQueryAndStream(view, msg.text, msg.files);
          break;
        case 'selectFiles':
          await this.selectFiles(view);
          break;
      }
    });
  }

  private getHtmlForWebview(
    webview: vscode.Webview,
    history: ChatMessage[]
  ): string {
    const nonce = getNonce();
    const historyJson = JSON.stringify(history);

    return /* html */`
      <!DOCTYPE html>
      <html lang="en">
      <head>
        <meta charset="UTF-8" />
        <meta http-equiv="Content-Security-Policy"
              content="default-src 'none'; script-src 'nonce-${nonce}'; style-src 'unsafe-inline';" />
        <style>
          :root {
            --vscode-chat-user-bg: var(--vscode-badge-background, #007ACC);
            --vscode-chat-user-fg: var(--vscode-badge-foreground, #ffffff);
            --vscode-chat-assistant-bg: var(--vscode-editor-background, #1e1e1e);
            --vscode-chat-assistant-fg: var(--vscode-editor-foreground, #cccccc);
            --vscode-chat-border: var(--vscode-panel-border, #2d2d30);
          }
          
          * { box-sizing: border-box; }
          
          body {
            font-family: var(--vscode-font-family);
            font-size: var(--vscode-font-size);
            margin: 0;
            padding: 0;
            display: flex;
            flex-direction: column;
            height: 100vh;
            background: var(--vscode-editor-background);
            color: var(--vscode-editor-foreground);
          }
          
          #history {
            flex: 1;
            overflow-y: auto;
            padding: 12px;
            display: flex;
            flex-direction: column;
            gap: 16px;
          }
          
          .message {
            display: flex;
            flex-direction: column;
            max-width: 100%;
          }
          
          .message-bubble {
            padding: 12px 16px;
            border-radius: 12px;
            word-wrap: break-word;
            white-space: pre-wrap;
            line-height: 1.4;
            position: relative;
          }
          
          .user .message-bubble {
            background: var(--vscode-chat-user-bg);
            color: var(--vscode-chat-user-fg);
            align-self: flex-end;
            margin-left: 20%;
            border-bottom-right-radius: 4px;
          }
          
          .assistant .message-bubble {
            background: var(--vscode-chat-assistant-bg);
            color: var(--vscode-chat-assistant-fg);
            align-self: flex-start;
            margin-right: 20%;
            border: 1px solid var(--vscode-chat-border);
            border-bottom-left-radius: 4px;
          }
          
          .message-header {
            font-size: 11px;
            opacity: 0.7;
            margin-bottom: 4px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
          }
          
          .user .message-header {
            text-align: right;
            color: var(--vscode-chat-user-fg);
          }
          
          .assistant .message-header {
            text-align: left;
            color: var(--vscode-chat-assistant-fg);
          }
          
          #input-container {
            border-top: 1px solid var(--vscode-chat-border);
            padding: 12px;
            background: var(--vscode-editor-background);
          }
          
          #input-area {
            display: flex;
            align-items: flex-end;
            gap: 8px;
          }
          
          #msg {
            flex: 1;
            min-height: 36px;
            max-height: 120px;
            padding: 8px 12px;
            border: 1px solid var(--vscode-input-border);
            border-radius: 6px;
            background: var(--vscode-input-background);
            color: var(--vscode-input-foreground);
            font-family: var(--vscode-font-family);
            font-size: var(--vscode-font-size);
            resize: none;
            outline: none;
          }
          
          #msg:focus {
            border-color: var(--vscode-focusBorder);
            box-shadow: 0 0 0 1px var(--vscode-focusBorder);
          }
          
          #send {
            padding: 8px 16px;
            background: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: var(--vscode-font-size);
            font-weight: 500;
            transition: background-color 0.15s ease;
          }
          
          #send:hover {
            background: var(--vscode-button-hoverBackground);
          }
          
          #send:disabled {
            background: var(--vscode-button-background);
            opacity: 0.5;
            cursor: not-allowed;
          }
          
          .loading {
            display: inline-flex;
            align-items: center;
            gap: 8px;
          }
          
          .typing-indicator {
            display: inline-flex;
            gap: 2px;
          }
          
          .typing-indicator div {
            width: 4px;
            height: 4px;
            border-radius: 50%;
            background: currentColor;
            opacity: 0.4;
            animation: typing 1.4s infinite ease-in-out;
          }
          
          .typing-indicator div:nth-child(1) { animation-delay: -0.32s; }
          .typing-indicator div:nth-child(2) { animation-delay: -0.16s; }
          
          @keyframes typing {
            0%, 80%, 100% { opacity: 0.4; }
            40% { opacity: 1; }
          }
          
          .empty-state {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100%;
            opacity: 0.6;
            text-align: center;
            padding: 32px;
          }
          
          .empty-state h3 {
            margin: 0 0 8px 0;
            font-size: 16px;
            font-weight: 600;
          }
          
          .empty-state p {
            margin: 0;
            font-size: 14px;
            line-height: 1.4;
          }
          
          #files-section {
            border-bottom: 1px solid var(--vscode-chat-border);
            padding: 8px 12px;
            background: var(--vscode-editor-background);
          }
          
          #attached-files {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-bottom: 8px;
          }
          
          .file-tag {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 4px 8px;
            background: var(--vscode-badge-background);
            color: var(--vscode-badge-foreground);
            border-radius: 4px;
            font-size: 12px;
            max-width: 200px;
          }
          
          .file-tag .filename {
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
          }
          
          .file-tag .remove {
            cursor: pointer;
            padding: 0 2px;
            border-radius: 2px;
            opacity: 0.7;
          }
          
          .file-tag .remove:hover {
            background: rgba(255, 255, 255, 0.1);
            opacity: 1;
          }
          
          #add-files {
            padding: 6px 12px;
            background: var(--vscode-button-secondaryBackground, var(--vscode-editor-background));
            color: var(--vscode-button-secondaryForeground, var(--vscode-editor-foreground));
            border: 1px solid var(--vscode-input-border);
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
            font-weight: 500;
            transition: all 0.15s ease;
          }
          
          #add-files:hover {
            background: var(--vscode-button-secondaryHoverBackground, var(--vscode-toolbar-hoverBackground));
          }
          
          #attached-files:empty {
            display: none;
          }
        </style>
      </head>
      <body>
        <div id="history"></div>
        <div id="input-container">
          <div id="files-section">
            <div id="attached-files"></div>
            <button id="add-files" type="button">📎 Add Files</button>
          </div>
          <div id="input-area">
            <textarea id="msg" rows="1" placeholder="Ask about your code..."></textarea>
            <button id="send">Send</button>
          </div>
        </div>

        <script nonce="${nonce}">
          const vscode = acquireVsCodeApi();
          let history = ${historyJson};
          let isLoading = false;
          let attachedFiles = [];

          const histEl = document.getElementById('history');
          const msgInput = document.getElementById('msg');
          const sendBtn = document.getElementById('send');
          const attachedFilesEl = document.getElementById('attached-files');
          const addFilesBtn = document.getElementById('add-files');
          const filesSectionEl = document.getElementById('files-section');

          function render() {
            if (history.length === 0) {
              histEl.innerHTML = \`
                <div class="empty-state">
                  <h3>Welcome to CodeChat!</h3>
                  <p>Ask me anything about your code.<br/>I can help with explanations, debugging, and suggestions.</p>
                </div>
              \`;
              return;
            }

            histEl.innerHTML = history.map(m => {
              const messageClass = m.role === 'user' ? 'user' : 'assistant';
              const header = m.role === 'user' ? 'You' : 'CodeChat';
              
              let content = escapeHtml(m.content);
              if (m.role === 'assistant' && m.isPartial) {
                content += \`
                  <div class="loading">
                    <div class="typing-indicator">
                      <div></div>
                      <div></div>
                      <div></div>
                    </div>
                  </div>
                \`;
              }
              
              return \`
                <div class="message \${messageClass}">
                  <div class="message-header">\${header}</div>
                  <div class="message-bubble">\${content}</div>
                </div>
              \`;
            }).join('');
            
            histEl.scrollTop = histEl.scrollHeight;
          }

          function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
          }

          function setLoading(loading) {
            isLoading = loading;
            sendBtn.disabled = loading;
            sendBtn.textContent = loading ? 'Sending...' : 'Send';
          }

          function autoResize() {
            msgInput.style.height = 'auto';
            msgInput.style.height = Math.min(msgInput.scrollHeight, 120) + 'px';
          }

          function renderAttachedFiles() {
            attachedFilesEl.innerHTML = attachedFiles.map(file => \`
              <div class="file-tag">
                <span class="filename" title="\${file}">\${file.split('/').pop()}</span>
                <span class="remove" onclick="removeFile('\${file}')" title="Remove file">×</span>
              </div>
            \`).join('');
          }

          function removeFile(filePath) {
            attachedFiles = attachedFiles.filter(f => f !== filePath);
            renderAttachedFiles();
          }

          function addFiles() {
            vscode.postMessage({ command: 'selectFiles' });
          }

          msgInput.addEventListener('input', autoResize);
          msgInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              sendMessage();
            }
          });

          function sendMessage() {
            const text = msgInput.value.trim();
            if (!text || isLoading) return;
            
            history.push({ role: 'user', content: text });
            render();
            setLoading(true);
            vscode.postMessage({ 
              command: 'send', 
              text: text,
              files: attachedFiles.length > 0 ? attachedFiles : undefined
            });
            msgInput.value = '';
            autoResize();
          }

          sendBtn.addEventListener('click', sendMessage);
          addFilesBtn.addEventListener('click', addFiles);

          // handle partial / final assistant messages and file selection
          window.addEventListener('message', event => {
            const msg = event.data;
            if (msg.role === 'assistant') {
              // Find last assistant message and update it, or create new one
              const lastMsg = history[history.length - 1];
              if (lastMsg && lastMsg.role === 'assistant' && lastMsg.isPartial) {
                lastMsg.content = msg.content;
                lastMsg.isPartial = msg.isPartial !== false;
              } else {
                history.push({ 
                  role: 'assistant', 
                  content: msg.content, 
                  isPartial: msg.isPartial !== false 
                });
              }
              
              if (!msg.isPartial) {
                setLoading(false);
              }
              render();
            } else if (msg.command === 'filesSelected') {
              // Add selected files to the list
              msg.files.forEach(filePath => {
                if (!attachedFiles.includes(filePath)) {
                  attachedFiles.push(filePath);
                }
              });
              renderAttachedFiles();
            }
          });

          // Expose removeFile function globally for onclick handlers
          window.removeFile = removeFile;

          // Initial render
          render();
          autoResize();
          renderAttachedFiles();
        </script>
      </body>
      </html>`;
  }

  private async selectFiles(view: vscode.WebviewView) {
    const uris = await vscode.window.showOpenDialog({
      canSelectMany: true,
      canSelectFiles: true,
      canSelectFolders: false,
      filters: {
        'All Files': ['*'],
        'Source Code': ['ts', 'js', 'py', 'java', 'cpp', 'c', 'cs', 'go', 'rs', 'php', 'rb', 'swift'],
        'Text Files': ['txt', 'md', 'json', 'yaml', 'yml', 'xml', 'html', 'css']
      },
      openLabel: 'Select Files for Context'
    });

    if (uris && uris.length > 0) {
      const filePaths = uris.map(uri => uri.fsPath);
      view.webview.postMessage({
        command: 'filesSelected',
        files: filePaths
      });
    }
  }

  private async postQueryAndStream(
    view: vscode.WebviewView,
    text: string,
    files?: string[]
  ) {
    const config = vscode.workspace.getConfiguration('codechat');
    const daemonUrl = config.get<string>('daemonUrl') || 'http://localhost:16005';

    // Build your QueryRequest
    const body = {
      provider: 'openai',
      model: 'o4-mini',
      history: [],    // you could load and pass previous history here
      message: text,
      files: files    // Send files array to backend
    };

    const res = await fetch(`${daemonUrl}/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });

    if (!res.body) {
      return;
    }

    // Stream parsing
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let assistantText = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      assistantText += decoder.decode(value, { stream: true });
      view.show?.(true);
      view.webview.postMessage({ 
        role: 'assistant', 
        content: assistantText,
        isPartial: true
      });
    }

    // Send final message to mark completion
    view.webview.postMessage({ 
      role: 'assistant', 
      content: assistantText,
      isPartial: false
    });

    // Persist last 50 messages
    const prev = this.ctx.workspaceState.get<ChatMessage[]>('chatHistory', []);
    const updated = [...prev, { role: 'user', content: text }, { role: 'assistant', content: assistantText }];
    this.ctx.workspaceState.update(
      'chatHistory',
      updated.slice(-50)
    );
  }
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  isPartial?: boolean;
}

function getNonce() {
  return Math.random().toString(36).substr(2, 9);
}

export function deactivate() {
  if (healthInterval) {
    clearInterval(healthInterval);
  }
  if (statusBarItem)
  {
    statusBarItem.dispose();
  }
}
