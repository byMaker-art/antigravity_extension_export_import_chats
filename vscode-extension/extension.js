const vscode = require('vscode');
const path = require('path');
const fs = require('fs');
const https = require('https');
const { execFile } = require('child_process');

let exportStatusBarItem;
let importStatusBarItem;
let syncStatusBarItem;
let conversationsProvider;

/**
 * Helper to fetch JSON via HTTPS with redirect support
 */
function fetchJson(url) {
    return new Promise((resolve, reject) => {
        https.get(url, { headers: { 'User-Agent': 'Antigravity-Chat-Sync-Updater' } }, res => {
            if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
                return fetchJson(res.headers.location).then(resolve).catch(reject);
            }
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                try {
                    resolve({ status: res.statusCode, data: JSON.parse(data) });
                } catch (e) {
                    resolve({ status: res.statusCode, raw: data });
                }
            });
        }).on('error', reject);
    });
}

function compareVersions(v1, v2) {
    const parse = (v) => v.replace(/^v/, '').split('.').map(n => parseInt(n, 10) || 0);
    const p1 = parse(v1);
    const p2 = parse(v2);
    for (let i = 0; i < Math.max(p1.length, p2.length); i++) {
        const num1 = p1[i] || 0;
        const num2 = p2[i] || 0;
        if (num1 > num2) return 1;
        if (num1 < num2) return -1;
    }
    return 0;
}

async function checkForUpdates(currentVersion, silent = false) {
    const config = vscode.workspace.getConfiguration('antigravity.chatSync');
    const repo = config.get('githubRepo') || 'byMaker-art/antigravity_extension_export_import_chats';

    try {
        const releaseRes = await fetchJson(`https://api.github.com/repos/${repo}/releases/latest`);
        let latestVersion = null;
        let releaseUrl = `https://github.com/${repo}/releases`;

        if (releaseRes.status === 200 && releaseRes.data && releaseRes.data.tag_name) {
            latestVersion = releaseRes.data.tag_name.replace(/^v/, '');
            releaseUrl = releaseRes.data.html_url || releaseUrl;
        } else {
            const rawRes = await fetchJson(`https://raw.githubusercontent.com/${repo}/main/vscode-extension/package.json`);
            if (rawRes.status === 200 && rawRes.data && rawRes.data.version) {
                latestVersion = rawRes.data.version;
            }
        }

        if (!latestVersion) {
            if (!silent) {
                vscode.window.showInformationMessage(`Antigravity Chat Sync: No remote releases found yet on repository: ${repo}.`);
            }
            return;
        }

        if (compareVersions(latestVersion, currentVersion) > 0) {
            const choice = await vscode.window.showInformationMessage(
                `🚀 Antigravity Chat Sync: New version v${latestVersion} is available! (Current: v${currentVersion})`,
                'Open GitHub Release',
                'How to Update',
                'Later'
            );
            if (choice === 'Open GitHub Release') {
                vscode.env.openExternal(vscode.Uri.parse(releaseUrl));
            } else if (choice === 'How to Update') {
                vscode.window.showInformationMessage(
                    'To update: git pull in the repository or download the latest release and run ./install_extension.sh'
                );
            }
        } else if (!silent) {
            vscode.window.showInformationMessage(`✓ Antigravity Chat Sync is up to date (v${currentVersion}).`);
        }
    } catch (err) {
        if (!silent) {
            vscode.window.showErrorMessage(`Update check failed: ${err.message || err}`);
        }
    }
}

/**
 * Executes the Python helper script with given arguments.
 */
function runSyncScript(args, projectPath, progressMessage) {
    const config = vscode.workspace.getConfiguration('antigravity.chatSync');
    const pythonPath = config.get('pythonPath') || 'python3';
    
    // Look for script in extension folder or workspace
    let scriptPath = path.join(__dirname, 'scripts', 'antigravity_chat_sync.py');
    if (!fs.existsSync(scriptPath)) {
        scriptPath = path.join(projectPath, 'antigravity_chat_sync.py');
    }

    return vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: progressMessage,
        cancellable: false
    }, () => {
        return new Promise((resolve, reject) => {
            const finalArgs = [scriptPath, ...args, '--dir', projectPath, '--json'];
            execFile(pythonPath, finalArgs, { encoding: 'utf8' }, (error, stdout, stderr) => {
                if (error) {
                    console.error('Antigravity Chat Sync Error:', stderr || error.message);
                    vscode.window.showErrorMessage(`Antigravity Chat Sync Failed: ${stderr || error.message}`);
                    return reject(error);
                }
                try {
                    const result = JSON.parse(stdout.trim());
                    resolve(result);
                } catch (e) {
                    resolve({ status: 'ok', raw: stdout.trim() });
                }
            });
        });
    });
}

/**
 * TreeDataProvider for the Conversations Sidebar View
 */
class ConversationsProvider {
    constructor() {
        this._onDidChangeTreeData = new vscode.EventEmitter();
        this.onDidChangeTreeData = this._onDidChangeTreeData.event;
        this.items = [];
    }

    refresh() {
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element) {
        return element;
    }

    async getChildren(element) {
        if (element) {
            return [];
        }
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (!workspaceFolders || workspaceFolders.length === 0) {
            return [new vscode.TreeItem('No folder opened in workspace')];
        }

        const projectPath = workspaceFolders[0].uri.fsPath;
        try {
            const res = await runSyncScript(['list'], projectPath, 'Loading conversations...');
            const convs = res.conversations || [];
            if (convs.length === 0) {
                const emptyItem = new vscode.TreeItem('No chats found for this project');
                emptyItem.description = 'Click [Export] or [Import]';
                emptyItem.iconPath = new vscode.ThemeIcon('info');
                return [emptyItem];
            }

            return convs.map(c => {
                const item = new vscode.TreeItem(c.title || '(Untitled conversation)', vscode.TreeItemCollapsibleState.None);
                item.description = `${c.step_count} steps | ${c.last_modified_time.slice(0, 10)}`;
                item.tooltip = `ID: ${c.conversation_id}\nLast Modified: ${c.last_modified_time}\nSteps: ${c.step_count}`;
                item.iconPath = new vscode.ThemeIcon('comment-discussion');
                item.contextValue = 'conversation';
                item.conversation = c;

                // Clicking item opens transcript if available
                const safeTitle = (c.title || c.conversation_id).replace(/[^\w\s.-]/g, '_').trim();
                const mdPath = path.join(projectPath, '.antigravity_chats', 'readable_transcripts', `${safeTitle}.md`);
                if (fs.existsSync(mdPath)) {
                    item.command = {
                        command: 'vscode.open',
                        title: 'Open Transcript',
                        arguments: [vscode.Uri.file(mdPath)]
                    };
                }
                return item;
            });
        } catch (err) {
            const errItem = new vscode.TreeItem('Error loading conversations');
            errItem.description = err.message;
            errItem.iconPath = new vscode.ThemeIcon('warning');
            return [errItem];
        }
    }
}

/**
 * Extension activation
 */
function activate(context) {
    // Register Sidebar Tree View
    conversationsProvider = new ConversationsProvider();
    vscode.window.registerTreeDataProvider('antigravityChatsView', conversationsProvider);

    // Register Status Bar Items
    const config = vscode.workspace.getConfiguration('antigravity.chatSync');
    const showStatusBar = config.get('showStatusBarButtons', true);

    if (showStatusBar) {
        // Export Button
        exportStatusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
        exportStatusBarItem.text = '$(cloud-upload) Export Chats';
        exportStatusBarItem.tooltip = 'Export Antigravity chats for this project into .antigravity_chats';
        exportStatusBarItem.command = 'antigravity.exportChats';
        exportStatusBarItem.show();
        context.subscriptions.push(exportStatusBarItem);

        // Import Button
        importStatusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 99);
        importStatusBarItem.text = '$(cloud-download) Import Chats';
        importStatusBarItem.tooltip = 'Import chats from .antigravity_chats into Antigravity IDE';
        importStatusBarItem.command = 'antigravity.importChats';
        importStatusBarItem.show();
        context.subscriptions.push(importStatusBarItem);

        // Sync Button
        syncStatusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 98);
        syncStatusBarItem.text = '$(sync) Sync Chats';
        syncStatusBarItem.tooltip = 'Smart bidirectional sync for Antigravity chats';
        syncStatusBarItem.command = 'antigravity.syncChats';
        syncStatusBarItem.show();
        context.subscriptions.push(syncStatusBarItem);
    }

    // Helper: get current project root
    function getWorkspacePath() {
        const folders = vscode.workspace.workspaceFolders;
        if (!folders || folders.length === 0) {
            vscode.window.showWarningMessage('Please open a project folder in Antigravity IDE first.');
            return null;
        }
        return folders[0].uri.fsPath;
    }

    // Command: Export Chats
    const exportCmd = vscode.commands.registerCommand('antigravity.exportChats', async () => {
        const projectPath = getWorkspacePath();
        if (!projectPath) return;

        try {
            const res = await runSyncScript(['export'], projectPath, 'Exporting project conversations...');
            if (res.status === 'ok') {
                const action = await vscode.window.showInformationMessage(
                    `✓ ${res.message}`,
                    'Open Folder in Finder',
                    'Refresh List'
                );
                if (action === 'Open Folder in Finder') {
                    const exportDir = path.join(projectPath, '.antigravity_chats');
                    vscode.env.openExternal(vscode.Uri.file(exportDir));
                }
                conversationsProvider.refresh();
            } else if (res.status === 'warning') {
                vscode.window.showWarningMessage(res.message);
            }
        } catch (e) {
            // Error already handled
        }
    });
    context.subscriptions.push(exportCmd);

    // Command: Import Chats
    const importCmd = vscode.commands.registerCommand('antigravity.importChats', async () => {
        const projectPath = getWorkspacePath();
        if (!projectPath) return;

        try {
            const res = await runSyncScript(['import'], projectPath, 'Importing conversations into Antigravity IDE...');
            if (res.status === 'ok') {
                vscode.window.showInformationMessage(`✓ ${res.message}`);
                conversationsProvider.refresh();
            }
        } catch (e) {
            // Error already handled
        }
    });
    context.subscriptions.push(importCmd);

    // Command: Smart Sync Chats
    const syncCmd = vscode.commands.registerCommand('antigravity.syncChats', async () => {
        const projectPath = getWorkspacePath();
        if (!projectPath) return;

        try {
            const res = await runSyncScript(['sync'], projectPath, 'Synchronizing Antigravity chats...');
            if (res.status === 'ok') {
                vscode.window.showInformationMessage(`✓ ${res.message}`);
                conversationsProvider.refresh();
            }
        } catch (e) {
            // Error already handled
        }
    });
    context.subscriptions.push(syncCmd);

    // Command: List / Refresh Chats
    const listCmd = vscode.commands.registerCommand('antigravity.listChats', () => {
        conversationsProvider.refresh();
    });
    context.subscriptions.push(listCmd);

    // Command: Open Transcript
    const openTranscriptCmd = vscode.commands.registerCommand('antigravity.openTranscript', (item) => {
        if (!item || !item.conversation) return;
        const projectPath = getWorkspacePath();
        if (!projectPath) return;

        const c = item.conversation;
        const safeTitle = (c.title || c.conversation_id).replace(/[^\w\s.-]/g, '_').trim();
        const mdPath = path.join(projectPath, '.antigravity_chats', 'readable_transcripts', `${safeTitle}.md`);
        if (fs.existsSync(mdPath)) {
            vscode.workspace.openTextDocument(mdPath).then(doc => vscode.window.showTextDocument(doc));
        } else {
            vscode.window.showInformationMessage(`Transcript not exported yet. Click "Export Chats" first.`);
        }
    });
    context.subscriptions.push(openTranscriptCmd);

    // Command: Check for Updates
    const checkUpdateCmd = vscode.commands.registerCommand('antigravity.checkUpdate', async () => {
        const extVersion = context.extension?.packageJSON?.version || '1.0.0';
        await checkForUpdates(extVersion, false);
    });
    context.subscriptions.push(checkUpdateCmd);

    // Auto-check updates on start if enabled
    if (config.get('autoCheckUpdates', true)) {
        const extVersion = context.extension?.packageJSON?.version || '1.0.0';
        setTimeout(() => {
            checkForUpdates(extVersion, true).catch(() => {});
        }, 3000);
    }

    // Auto-import on open if enabled in settings
    if (config.get('autoImportOnOpen', false)) {
        const projectPath = getWorkspacePath();
        if (projectPath) {
            const exportDir = path.join(projectPath, '.antigravity_chats');
            if (fs.existsSync(exportDir)) {
                runSyncScript(['sync'], projectPath, 'Auto-syncing Antigravity chats...')
                    .then(() => conversationsProvider.refresh())
                    .catch(() => {});
            }
        }
    }
}

function deactivate() {
    if (exportStatusBarItem) exportStatusBarItem.dispose();
    if (importStatusBarItem) importStatusBarItem.dispose();
    if (syncStatusBarItem) syncStatusBarItem.dispose();
}

module.exports = {
    activate,
    deactivate
};
