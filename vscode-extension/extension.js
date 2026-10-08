
const vscode = require('vscode');
const fs = require('fs');
const os = require('os');
const path = require('path');

let statusItem;
let outputChannel;
let hasStartedThisWindow = false;

const ENERGY_OPTIONS = [
  'Fine',
  'Tired',
  'Burned out',
  'Completely wiped out'
];

const AFTER_EFFECT_OPTIONS = [
  'Nothing unusual',
  'Needed significant rest',
  'Could not do another task',
  'Needed to lie down/sleep',
  'Needed help with something'
];

function config() {
  const c = vscode.workspace.getConfiguration('barklyWorkLog');

  return {
    url: c.get('url', 'http://127.0.0.1:8766').replace(/\/$/, ''),
    category: c.get('category', 'Barkly Labs'),
    autoStart: c.get('autoStart', true)
  };
}

function token() {
  const tokenPath = path.join(os.homedir(), '.barkly_work_log_token');

  try {
    return fs.readFileSync(tokenPath, 'utf8').trim();
  } catch (_) {
    throw new Error(
      `Cannot read ${tokenPath}. Start the Barkly Work Log Python server first.`
    );
  }
}

async function request(endpoint, payload = {}) {
  const c = config();

  const response = await fetch(`${c.url}${endpoint}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Barkly-Token': token()
    },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(5000)
  });

  const data = await response.json();

  if (!response.ok || !data.ok) {
    throw new Error(
      data.error || `Logger returned HTTP ${response.status}`
    );
  }

  return data;
}

function updateStatus(text) {
  if (statusItem) {
    statusItem.text = `$(watch) Barkly: ${text}`;
  }
}

async function start(showMessage = false) {
  if (!vscode.workspace.workspaceFolders?.length) {
    if (showMessage) {
      vscode.window.showInformationMessage(
        'Barkly Work Log: open a workspace folder first.'
      );
    }
    return;
  }

  try {
    const workspace = vscode.workspace.workspaceFolders
      .map(folder => folder.name)
      .join(', ');

    const result = await request('/vscode/start', {
      category: config().category,
      workspace
    });

    hasStartedThisWindow = true;
    updateStatus('tracking');

    if (showMessage) {
      vscode.window.showInformationMessage(
        result.already_tracking
          ? 'A Barkly VS Code session is already being tracked.'
          : 'Barkly Work Log: VS Code session started.'
      );
    }
  } catch (error) {
    updateStatus('offline');

    if (outputChannel) {
      outputChannel.appendLine(`Start failed: ${error.stack || error.message}`);
    }

    vscode.window.showWarningMessage(
      `Barkly Work Log could not start tracking: ${error.message}`
    );
  }
}

function askPick(title, placeholder, items, options = {}) {
  return vscode.window.showQuickPick(items, {
    title,
    placeHolder: placeholder,
    ignoreFocusOut: true,
    ...options
  });
}

function askText(title, prompt, placeHolder = 'Optional — press Enter to continue') {
  return vscode.window.showInputBox({
    title,
    prompt,
    placeHolder,
    ignoreFocusOut: true
  });
}

// Accepts "90", "90m", "1h 30m", "45s", etc.
// A plain number means minutes, matching the Python logger.
function durationToSeconds(value) {
  const text = String(value || '').trim().toLowerCase();

  if (!text) return 0;

  const matches = [
    ...text.matchAll(
      /(\d+(?:\.\d+)?)\s*(h|hr|hrs|hour|hours|m|min|mins|minute|minutes|s|sec|secs|second|seconds)/g
    )
  ];

  if (matches.length) {
    return Math.round(
      matches.reduce((total, match) => {
        const number = Number(match[1]);
        const unit = match[2];

        if (unit.startsWith('h')) return total + number * 3600;
        if (unit.startsWith('m')) return total + number * 60;

        return total + number;
      }, 0)
    );
  }

  if (/^\d+(?:\.\d+)?$/.test(text)) {
    return Math.round(Number(text) * 60);
  }

  return null;
}

async function collectSessionReport() {
  const energy = await askPick(
    'Barkly Work Log · Your status',
    'How did you feel by the end of this session?',
    ENERGY_OPTIONS
  );

  if (!energy) return null;

  const afterEffect = await askPick(
    'Barkly Work Log · After-effects',
    'What happened after working?',
    AFTER_EFFECT_OPTIONS
  );

  if (!afterEffect) return null;

  const activeTime = await askText(
    'Barkly Work Log · Active work',
    'About how long were you actively working? Exclude breaks and long periods waiting for tools.',
    'Example: 1h 30m (a plain number means minutes)'
  );

  if (activeTime === undefined) return null;

  const activeSeconds = durationToSeconds(activeTime);

  if (activeSeconds === null) {
    vscode.window.showWarningMessage(
      'Enter active time like "45m", "1h 30m", or "90".'
    );
    return collectSessionReport();
  }

  const breakTime = await askText(
    'Barkly Work Log · Break time',
    'Approximately how much time did you spend on breaks?',
    'Example: 1h or 20m; blank if none'
  );

  if (breakTime === undefined) return null;

  const breakSeconds = durationToSeconds(breakTime);

  if (breakSeconds === null) {
    vscode.window.showWarningMessage(
      'Enter break time like "20m" or "1h", or leave it blank.'
    );
    return collectSessionReport();
  }

  const breaksText = await askText(
    'Barkly Work Log · Number of breaks',
    'How many breaks did you take?',
    'Example: 3'
  );

  if (breaksText === undefined) return null;

  const breaks = breaksText.trim() === '' ? 0 : Number(breaksText);

  if (!Number.isInteger(breaks) || breaks < 0) {
    vscode.window.showWarningMessage(
      'Enter a whole number of breaks, such as 0, 1, or 3.'
    );
    return collectSessionReport();
  }

  const symptoms = await askPick(
    'Barkly Work Log · Symptoms and limitations',
    'Select all that applied during or after this session.',
    [
      'Fatigue / low energy',
      'Brain fog / memory difficulty',
      'Difficulty concentrating',
      'Overwhelm / sensory stress',
      'Pain or physical discomfort',
      'Anxiety / emotional strain',
      'Needed extra breaks',
      'No notable symptoms'
    ],
    { canPickMany: true }
  );

  if (symptoms === undefined) return null;

  const continuation = await askPick(
    'Barkly Work Log · Work capacity',
    'At the end of this session, could you reasonably continue working?',
    [
      'Yes, I could continue',
      'Only with a longer break',
      'No, I needed to stop',
      'Continuing would likely make things worse',
      'Unsure'
    ]
  );

  if (!continuation) return null;

  const recovery = await askPick(
    'Barkly Work Log · Recovery needs',
    'What did you need after the session?',
    [
      'No extra recovery needed',
      'A normal break before another task',
      'A longer rest period',
      'Needed to lie down or sleep',
      'Could not manage other tasks afterward',
      'Needed help with daily activities'
    ]
  );

  if (!recovery) return null;

  const outcome = await askText(
    'Barkly Work Log · Work completed',
    'What did you accomplish? What remained unfinished, or were you waiting on something?',
    'Optional — briefly describe the session'
  );

  if (outcome === undefined) return null;

  const support = await askText(
    'Barkly Work Log · Support and context',
    'Did you need help, experience interruptions, or have anything else affect your capacity?',
    'Optional — support, interruptions, waiting, or other context'
  );

  if (support === undefined) return null;

  const extraNotes = await askText(
    'Barkly Work Log · Additional notes',
    'Anything else you want recorded about this session or its effects?',
    'Optional'
  );

  if (extraNotes === undefined) return null;

  const symptomsList = Array.isArray(symptoms)
    ? symptoms
    : (symptoms ? [symptoms] : []);

  const notes = [
    'VS Code work-capacity check-in:',
    `Estimated active work: ${activeTime.trim() || 'Not recorded'}`,
    `Estimated break time: ${breakTime.trim() || '0'}`,
    `Number of breaks: ${breaks}`,
    `Symptoms / limitations: ${
      symptomsList.length ? symptomsList.join(', ') : 'Not recorded'
    }`,
    `Could continue: ${continuation}`,
    `Recovery needed: ${recovery}`,
    `Work completed / unfinished / waiting: ${outcome.trim() || 'Not recorded'}`,
    `Support / interruptions / context: ${support.trim() || 'Not recorded'}`,
    `Additional notes: ${extraNotes.trim() || 'None'}`
  ].join('\n');

  return {
    energy,
    after_effect: afterEffect,
    active_seconds: activeSeconds,
    break_seconds: breakSeconds,
    breaks,
    notes
  };
}

async function stop(showMessage = false, collectEffects = true) {
  let effects = {};

  if (collectEffects) {
    const report = await collectSessionReport();

    // Cancelling the questionnaire leaves the session tracking.
    if (!report) return;

    effects = report;
  }

  try {
    const result = await request('/vscode/stop', effects);

    hasStartedThisWindow = false;
    updateStatus('not tracking');

    if (showMessage) {
      vscode.window.showInformationMessage(
        result.stopped
          ? 'Barkly Work Log: session and capacity check-in saved.'
          : 'Barkly Work Log: no open session to stop.'
      );
    }
  } catch (error) {
    updateStatus('stop failed');

    if (outputChannel) {
      outputChannel.appendLine(`Stop failed: ${error.stack || error.message}`);
    }

    vscode.window.showWarningMessage(
      `Barkly Work Log could not stop tracking: ${error.message}`
    );
  }
}

function activate(context) {
  outputChannel = vscode.window.createOutputChannel('Barkly Work Log');
  context.subscriptions.push(outputChannel);
  outputChannel.appendLine('Barkly Work Log extension activated.');

  statusItem = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Left,
    10
  );

  statusItem.command = 'barklyWorkLog.showStatus';
  statusItem.tooltip = 'Click to view Barkly Work Log tracking status';
  statusItem.show();

  context.subscriptions.push(statusItem);

  context.subscriptions.push(
    vscode.commands.registerCommand(
      'barklyWorkLog.start',
      () => start(true)
    )
  );

  context.subscriptions.push(
    vscode.commands.registerCommand(
      'barklyWorkLog.stop',
      () => stop(true, true)
    )
  );

  context.subscriptions.push(
    vscode.commands.registerCommand(
      'barklyWorkLog.showStatus',
      async () => {
        const choice = await vscode.window.showQuickPick(
          [
            'Start tracking',
            'Stop tracking and check in',
            'Open Barkly Work Log'
          ],
          { placeHolder: 'Barkly Work Log' }
        );

        if (choice === 'Start tracking') {
          await start(true);
        } else if (choice === 'Stop tracking and check in') {
          await stop(true, true);
        } else if (choice === 'Open Barkly Work Log') {
          vscode.env.openExternal(vscode.Uri.parse(config().url));
        }
      }
    )
  );

  if (config().autoStart && vscode.workspace.workspaceFolders?.length) {
    start(false);
  }
}

async function deactivate() {
  // Do not show interactive prompts during shutdown.
  // Save neutral defaults and explicitly note that no detailed check-in occurred.
  if (hasStartedThisWindow) {
    try {
      await request('/vscode/stop', {
        energy: 'Fine',
        after_effect: 'Nothing unusual',
        notes:
          'VS Code closed before the detailed work-capacity check-in was completed. ' +
          'Active work, breaks, symptoms, and recovery were not assessed.'
      });
    } catch (error) {
      if (outputChannel) {
        outputChannel.appendLine(
          `Shutdown save failed: ${error.stack || error.message}`
        );
      }
    }
  }
}

module.exports = { activate, deactivate };