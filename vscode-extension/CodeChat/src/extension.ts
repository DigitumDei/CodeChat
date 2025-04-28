import * as vscode from 'vscode';
import axios from 'axios';

let statusBarItem: vscode.StatusBarItem;
let healthInterval: NodeJS.Timeout;

export function activate(context: vscode.ExtensionContext) {
  // 1) create a status bar item
  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  statusBarItem.text = `CodeChat: $(sync~spin) Checking…`;
  statusBarItem.show();
  context.subscriptions.push(statusBarItem);

  // 2) health-check function
  async function checkHealth() {
    try {
      const res = await axios.get('http://localhost:16005/health', { timeout: 5000 });
      if (res.status === 200 && res.data?.status === 'ok') {
        // mark healthy
        await vscode.commands.executeCommand('setContext', 'codechat.status', 'healthy');
        statusBarItem.text = `CodeChat: $(check) Healthy`;
      } else {
        throw new Error(`bad status: ${res.status}`);
      }
    } catch (err) {
      // mark offline
      await vscode.commands.executeCommand('setContext', 'codechat.status', 'offline');
      statusBarItem.text = `CodeChat: $(error) Offline`;
    }
  }

  // 3) run immediately, then every 30s
  checkHealth();
  healthInterval = setInterval(checkHealth, 30_000);

  // 4) your existing helloWorld command
  const disposable = vscode.commands.registerCommand(
    'codechat.helloWorld',
    () => vscode.window.showInformationMessage('CodeChat extension wired up!'));
  context.subscriptions.push(disposable);
}

export function deactivate() {
  if (healthInterval) {
    clearInterval(healthInterval);
  }
  if (statusBarItem) {
    statusBarItem.dispose();
  }
}
