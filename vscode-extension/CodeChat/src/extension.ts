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
