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

		// 5) register "open settings" command
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

  // 6) register "open chat" command
  const openChat = vscode.commands.registerCommand(
    'codechat.openChat',
    () => {
      vscode.commands.executeCommand('codechat.chat.focus');
    }
  );
  context.subscriptions.push(openChat);

  // 7) register "clear history" command  
  const clearHistory = vscode.commands.registerCommand(
    'codechat.clearHistory',
    () => {
      context.workspaceState.update('chatHistory', []);
      vscode.window.showInformationMessage('CodeChat: Chat history cleared');
    }
  );
  context.subscriptions.push(clearHistory);

  console.log('🔌 CodeChat extension activated');
  
  // Create the chat view provider instance so we can reference it
  const chatProvider = new ChatViewProvider(context);
  
  // 8) register "ask about file" command
  const askAboutFile = vscode.commands.registerCommand(
    'codechat.askAboutFile',
    async (uri?: vscode.Uri) => {
      const fileUri = uri || vscode.window.activeTextEditor?.document.uri;
      if (!fileUri) {
        vscode.window.showWarningMessage('No file selected');
        return;
      }
      
      // Add the file to chat and focus the view
      chatProvider.addFileToChat(fileUri.fsPath);
      vscode.commands.executeCommand('codechat.chat.focus');
    }
  );
  context.subscriptions.push(askAboutFile);
  
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(
      'codechat.chat',
      chatProvider,
      {
        // so that your React/vanilla bundle survives when hidden
        webviewOptions: { retainContextWhenHidden: true }
      }
    )
  );
}

class ChatViewProvider implements vscode.WebviewViewProvider {
  private _view?: vscode.WebviewView;
  
  constructor(private ctx: vscode.ExtensionContext) {}

  public resolveWebviewView(
    view: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext
  ) {
    this._view = view;
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
          
          /* Markdown formatting styles */
          .message-bubble h1, .message-bubble h2, .message-bubble h3 {
            margin: 12px 0 8px 0;
            line-height: 1.3;
          }
          
          .message-bubble h1 { font-size: 20px; font-weight: 700; }
          .message-bubble h2 { font-size: 18px; font-weight: 600; }
          .message-bubble h3 { font-size: 16px; font-weight: 600; }
          
          .message-bubble strong { font-weight: 600; }
          .message-bubble em { font-style: italic; }
          
          .message-bubble ul {
            margin: 8px 0;
            padding-left: 20px;
          }
          
          .message-bubble li {
            margin: 4px 0;
            line-height: 1.4;
          }
          
          .message-bubble a {
            color: var(--vscode-textLink-foreground);
            text-decoration: none;
          }
          
          .message-bubble a:hover {
            text-decoration: underline;
          }
          
          .inline-code {
            background: var(--vscode-textCodeBlock-background);
            color: var(--vscode-editor-foreground);
            padding: 2px 4px;
            border-radius: 3px;
            font-family: var(--vscode-editor-font-family, 'Monaco', 'Consolas', monospace);
            font-size: 0.9em;
          }
          
          .code-block {
            margin: 12px 0;
            border: 1px solid var(--vscode-chat-border);
            border-radius: 6px;
            background: var(--vscode-textCodeBlock-background);
            overflow: hidden;
          }
          
          .code-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 12px;
            background: var(--vscode-editor-background);
            border-bottom: 1px solid var(--vscode-chat-border);
            font-size: 12px;
          }
          
          .code-lang {
            color: var(--vscode-editor-foreground);
            font-weight: 500;
            opacity: 0.8;
          }
          
          .code-content {
            margin: 0;
            padding: 12px;
            background: var(--vscode-textCodeBlock-background);
            color: var(--vscode-editor-foreground);
            font-family: var(--vscode-editor-font-family, 'Monaco', 'Consolas', monospace);
            font-size: 13px;
            line-height: 1.4;
            overflow-x: auto;
          }
          
          .code-content code {
            background: none;
            padding: 0;
            border-radius: 0;
            font-family: inherit;
          }
          
          .copy-btn, .copy-code-btn {
            background: none;
            border: none;
            color: var(--vscode-editor-foreground);
            cursor: pointer;
            padding: 4px 6px;
            border-radius: 3px;
            font-size: 12px;
            opacity: 0.6;
            transition: opacity 0.15s ease, background-color 0.15s ease;
          }
          
          .copy-btn:hover, .copy-code-btn:hover {
            opacity: 1;
            background: rgba(255, 255, 255, 0.1);
          }
          
          .message-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
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
              
              let content = m.role === 'assistant' ? formatMarkdown(m.content) : escapeHtml(m.content);
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
                  <div class="message-header">
                    \${header}
                    \${m.role === 'assistant' ? '<button class="copy-btn" onclick="copyMessage(\`' + escapeHtml(m.content).replace(/\`/g, '\\\`') + '\`)" title="Copy message">📋</button>' : ''}
                  </div>
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

          function formatMarkdown(text) {
            if (!text) return '';
            
            let html = escapeHtml(text);
            
            // Code blocks with syntax highlighting  
            html = html.replace(/\`\`\`(\\w+)?\\n([\\s\\S]*?)\\n\`\`\`/g, (match, lang, code) => {
              const language = lang || 'text';
              const codeId = 'code_' + Math.random().toString(36).substr(2, 9);
              // Store the code content in a data attribute instead of onclick parameter
              return '<div class="code-block">' +
                '<div class="code-header">' +
                  '<span class="code-lang">' + language + '</span>' +
                  '<button class="copy-code-btn" data-code="' + escapeHtml(code) + '" onclick="copyCodeFromButton(this)" title="Copy code">📋</button>' +
                '</div>' +
                '<pre class="code-content"><code class="language-' + language + '">' + code + '</code></pre>' +
              '</div>';
            });
            
            // Inline code
            html = html.replace(/\`([^\`]+)\`/g, '<code class="inline-code">$1</code>');
            
            // Headers
            html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
            html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
            html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');
            
            // Bold and italic
            html = html.replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>');
            html = html.replace(/\\*(.*?)\\*/g, '<em>$1</em>');
            
            // Lists
            html = html.replace(/^\\* (.*$)/gim, '<li>$1</li>');
            html = html.replace(/^\\d+\\. (.*$)/gim, '<li>$1</li>');
            
            // Wrap consecutive <li> elements in <ul>
            html = html.replace(/((<li>.*<\\/li>\\s*)+)/g, '<ul>$1</ul>');
            
            // Links
            html = html.replace(/\\[([^\\]]+)\\]\\(([^\\)]+)\\)/g, '<a href="$2" target="_blank">$1</a>');
            
            // Line breaks
            html = html.replace(/\\n/g, '<br>');
            
            return html;
          }

          function copyMessage(text) {
            if (navigator.clipboard && navigator.clipboard.writeText) {
              navigator.clipboard.writeText(text).then(() => {
                console.log('Message copied to clipboard');
              }).catch(err => {
                console.error('Failed to copy message:', err);
                fallbackCopyTextToClipboard(text);
              });
            } else {
              fallbackCopyTextToClipboard(text);
            }
          }

          function copyCode(code, buttonEl) {
            if (navigator.clipboard && navigator.clipboard.writeText) {
              navigator.clipboard.writeText(code).then(() => {
                const originalText = buttonEl.innerHTML;
                buttonEl.innerHTML = '✅';
                setTimeout(() => {
                  buttonEl.innerHTML = originalText;
                }, 2000);
              }).catch(err => {
                console.error('Failed to copy code:', err);
                fallbackCopyTextToClipboard(code);
              });
            } else {
              fallbackCopyTextToClipboard(code);
            }
          }

          function copyCodeFromButton(buttonEl) {
            const code = buttonEl.getAttribute('data-code');
            if (code) {
              copyCode(code, buttonEl);
            }
          }

          function fallbackCopyTextToClipboard(text) {
            const textArea = document.createElement("textarea");
            textArea.value = text;
            textArea.style.top = "0";
            textArea.style.left = "0";
            textArea.style.position = "fixed";
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();
            try {
              const successful = document.execCommand('copy');
              if (successful) {
                console.log('Fallback: Text copied to clipboard');
              }
            } catch (err) {
              console.error('Fallback: Unable to copy text', err);
            }
            document.body.removeChild(textArea);
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
            attachedFilesEl.innerHTML = attachedFiles.map((file, index) => \`
              <div class="file-tag">
                <span class="filename" title="\${file}">\${file.split('/').pop()}</span>
                <span class="remove" onclick="removeFileByIndex(\${index})" title="Remove file">×</span>
              </div>
            \`).join('');
          }

          function removeFile(filePath) {
            attachedFiles = attachedFiles.filter(f => f !== filePath);
            renderAttachedFiles();
          }

          function removeFileByIndex(index) {
            attachedFiles.splice(index, 1);
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

          // Expose functions globally for onclick handlers
          window.removeFile = removeFile;
          window.removeFileByIndex = removeFileByIndex;
          window.copyMessage = copyMessage;
          window.copyCode = copyCode;
          window.copyCodeFromButton = copyCodeFromButton;

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

    // Convert local file paths to daemon container paths
    let containerFiles: string[] | undefined;
    if (files && files.length > 0) {
      const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
      if (workspaceRoot) {
        containerFiles = files.map(filePath => {
          // Convert absolute local path to relative path from workspace root
          let relativePath = vscode.workspace.asRelativePath(filePath);
          
          // Normalize path separators to forward slashes for container
          relativePath = relativePath.replace(/\\\\/g, '/');
          
          // Remove any remaining drive letters (Windows)
          relativePath = relativePath.replace(/^[a-zA-Z]:/, '');
          
          // Ensure it starts with a clean path
          if (relativePath.startsWith('/')) {
            relativePath = relativePath.substring(1);
          }
          
          // Convert to container path (mounted at /workspace)
          return `/workspace/${relativePath}`;
        });
      } else {
        // Fallback if no workspace folder
        containerFiles = files;
      }
    }

    // Build your QueryRequest
    const body = {
      provider: 'openai',
      model: 'o4-mini',
      history: [],    // you could load and pass previous history here
      message: text,
      files: containerFiles    // Send container-accessible paths to backend
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
      if (done) {
        break;
      }
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

  public addFileToChat(filePath: string) {
    if (this._view) {
      this._view.webview.postMessage({
        command: 'filesSelected',
        files: [filePath]
      });
      this._view.show?.(true);
    }
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
