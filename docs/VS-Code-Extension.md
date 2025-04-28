## 🐶 Telemetry-Free Dog-Food Build

This is an early, telemetry-free build of the CodeChat VS Code extension for internal dog-fooding. No usage data, errors, or user identifiers are sent anywhere.

### Manual Installation (Early Testers)

1. **Prerequisites**  
   - [Node.js](https://nodejs.org/) ≥ 14  
   - VS Code installed  
   - The [vsce](https://marketplace.visualstudio.com/items?itemName=eg2.vscode-vsce) packaging tool:  
     ```bash
     npm install -g vsce
     ```

2. **Clone & Build**  
   ```bash
   git clone https://github.com/DigitumDei/CodeChat.git
   cd CodeChat/vscode-extension/CodeChat
   npm install
   npm run build   # e.g. webpack or tsc for your extension
   ```

3. **Package as VSIX**  
   ```bash
   vsce package --pre-release
   # produces `codechat-<version>.vsix`
   ```

4. **Install into VS Code**  
   ```bash
   code --install-extension codechat-<version>.vsix
   ```

5. **Launch Extension Development Host**  
   - Open the Command Palette (⇧⌘P / Ctrl+Shift+P) → **Developer: Reload Window**  
   - Or run **Extension Development Host** from your Debug panel.

Once installed, your running VS Code will have the latest dog-food build—no telemetry, just chat!  