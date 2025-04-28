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
          await this.postQueryAndStream(view, msg.text);
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
          body { font-family: sans-serif; margin: 0; padding: 0; display: flex; flex-direction: column; height: 100vh; }
          #history { flex: 1; overflow: auto; padding: 8px; }
          #input { display: flex; }
          #input textarea { flex: 1; }
        </style>
      </head>
      <body>
        <div id="history"></div>
        <div id="input">
          <textarea id="msg" rows="2"></textarea>
          <button id="send">Send</button>
        </div>

        <script nonce="${nonce}">
          const vscode = acquireVsCodeApi();
          let history = ${historyJson};

          const histEl = document.getElementById('history');
          function render() {
            histEl.innerHTML = history.map(m =>
              '<div><b>' + m.role + ':</b> ' + m.content + '</div>'
            ).join('');
            histEl.scrollTop = histEl.scrollHeight;
          }
          render();

          document.getElementById('send').addEventListener('click', () => {
            const text = document.getElementById('msg').value;
            if (!text) return;
            history.push({ role: 'user', content: text });
            render();
            vscode.postMessage({ command: 'send', text });
            document.getElementById('msg').value = '';
          });

          // handle partial / final assistant messages
          window.addEventListener('message', event => {
            const msg = event.data;
            if (msg.role === 'assistant') {
              history.push({ role: 'assistant', content: msg.content });
              render();
            }
          });
        </script>
      </body>
      </html>`;
  }

  private async postQueryAndStream(
    view: vscode.WebviewView,
    text: string
  ) {
    const config = vscode.workspace.getConfiguration('codechat');
    const daemonUrl = config.get<string>('daemonUrl') || 'http://localhost:16005';

    // Build your QueryRequest
    const body = {
      provider: 'openai',
      model: 'o4-mini',
      history: [],    // you could load and pass previous history here
      message: text
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
      view.webview.postMessage({ role: 'assistant', content: assistantText });
    }

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
