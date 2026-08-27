"""HTTP entry point and lightweight developer UI for internal AI debugging.

This router delegates strictly to DebugRunner and does NOT duplicate pipeline,
retrieval, prompt construction, or generation logic.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from src.api.contracts import DebugRunRequest
from src.observability.debug_runner import DebugRunner, LAYERS

router = APIRouter(prefix="/internal/debug", tags=["debug"])

_DEBUG_UI_HTML = r"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Enterprise AI Copilot Studio - Developer Debugger</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400;1,500&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    body {
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }
    .mono, pre, code, .font-mono {
      font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-feature-settings: "liga" on, "calt" on, "zero" on;
    }
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: #0B0D13; }
    ::-webkit-scrollbar-thumb { background: #1F2430; border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: #2E3547; }
  </style>
</head>
<body class="bg-[#0B0D13] text-[#E2E8F0] min-h-screen p-6 antialiased selection:bg-blue-600 selection:text-white">

  <!-- Header -->
  <header class="max-w-7xl mx-auto flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-6 border-b border-[#1F2430]">
    <div class="flex items-center gap-3.5">
      <div class="w-9 h-9 rounded-xl bg-blue-600 flex items-center justify-center font-bold text-white text-sm shadow-sm tracking-tight">AI</div>
      <div>
        <h1 class="text-lg font-bold text-zinc-100 tracking-tight">Enterprise AI Copilot Studio</h1>
        <p class="text-xs text-zinc-400 font-medium mt-0.5">Text-to-SQL Pipeline Developer Debugger & MLflow 3 Tracing</p>
      </div>
    </div>
    <div class="flex flex-wrap items-center gap-2">
      <a href="http://127.0.0.1:5000/#/experiments/1/traces" target="_blank" class="px-3 py-1.5 rounded-lg border border-[#1F2430] bg-[#12151D] hover:bg-[#1A1F2C] text-xs font-semibold text-zinc-300 transition flex items-center gap-1.5">
        <span>📊</span> MLflow Traces
      </a>
      <a href="http://127.0.0.1:5000/#/prompts" target="_blank" class="px-3 py-1.5 rounded-lg border border-[#1F2430] bg-[#12151D] hover:bg-[#1A1F2C] text-xs font-semibold text-zinc-300 transition flex items-center gap-1.5">
        <span>📑</span> Prompts Registry
      </a>
    </div>
  </header>

  <!-- Main Grid -->
  <main class="max-w-7xl mx-auto grid grid-cols-12 gap-6 mt-6">

    <!-- Left Column (Controls & Query) -->
    <section class="col-span-12 lg:col-span-5 flex flex-col gap-4">
      <div class="bg-[#12151D] border border-[#1F2430] rounded-xl p-5 flex flex-col gap-3.5 shadow-sm">
        <label class="text-xs font-bold uppercase tracking-wider text-zinc-400">Natural Language Query</label>
        
        <!-- Presets -->
        <div class="flex flex-wrap gap-1.5">
          <button onclick="setPreset('Show all active customers with their account balance')" class="px-2.5 py-1 text-xs font-medium bg-[#181C26] hover:bg-[#202634] text-zinc-300 rounded-md border border-[#242B3B] transition cursor-pointer">Active Customers</button>
          <button onclick="setPreset('Show transactions for customer 101 in the last 30 days')" class="px-2.5 py-1 text-xs font-medium bg-[#181C26] hover:bg-[#202634] text-zinc-300 rounded-md border border-[#242B3B] transition cursor-pointer">Customer 101 Txns</button>
          <button onclick="setPreset('Find merchants with total spending greater than 50000')" class="px-2.5 py-1 text-xs font-medium bg-[#181C26] hover:bg-[#202634] text-zinc-300 rounded-md border border-[#242B3B] transition cursor-pointer">Spending > $50k</button>
          <button onclick="setPreset('List active loans grouped by branch name with total amount')" class="px-2.5 py-1 text-xs font-medium bg-[#181C26] hover:bg-[#202634] text-zinc-300 rounded-md border border-[#242B3B] transition cursor-pointer">Branch Loans</button>
        </div>

        <textarea id="questionInput" rows="4" class="w-full bg-[#090B10] border border-[#1F2430] focus:border-blue-500 focus:outline-none rounded-lg p-3 text-sm text-zinc-200 placeholder-zinc-500 resize-none leading-relaxed transition" placeholder="Enter your business question here...">Show all active customers with their account balance</textarea>

        <div class="flex flex-col gap-1.5">
          <label class="text-xs font-medium text-zinc-400">Execution Scope</label>
          <select id="layerSelect" class="w-full bg-[#090B10] border border-[#1F2430] focus:border-blue-500 focus:outline-none rounded-lg p-2.5 text-xs font-medium text-zinc-300 cursor-pointer">
            <option value="full">Full Flow (Retrieval → Prompt → LLM → Validation → SQL)</option>
            <option value="generation">Generation Only (Skip Validation Engine)</option>
            <option value="retrieval">Retrieval Only (Semantic Search)</option>
            <option value="prompt">Prompt Only (Context Builder)</option>
          </select>
        </div>

        <button id="runBtn" onclick="runDebugFlow()" class="w-full bg-blue-600 hover:bg-blue-500 active:scale-[0.99] text-white font-semibold text-sm py-2.5 rounded-lg transition duration-150 flex items-center justify-center gap-2 shadow-sm cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed">
          <span id="btnIcon">⚡</span>
          <span id="btnText">Execute Debug Run & Log Trace</span>
        </button>
      </div>

      <!-- Stage Breakdown Table -->
      <div class="bg-[#12151D] border border-[#1F2430] rounded-xl p-5 flex flex-col gap-3 shadow-sm">
        <div class="flex items-center justify-between">
          <h2 class="text-xs font-bold uppercase tracking-wider text-zinc-400">Pipeline Stage Breakdown</h2>
          <span id="stoppingBadge" class="text-xs font-mono font-medium text-zinc-500">--</span>
        </div>
        <div class="overflow-hidden rounded-lg border border-[#1F2430]">
          <table class="w-full text-left text-xs border-collapse">
            <thead>
              <tr class="bg-[#141720] text-zinc-400 border-b border-[#1F2430]">
                <th class="py-2.5 px-3 font-semibold">Stage</th>
                <th class="py-2.5 px-3 font-semibold">Status</th>
                <th class="py-2.5 px-3 font-semibold text-right">Duration</th>
              </tr>
            </thead>
            <tbody id="stageTableBody" class="divide-y divide-[#1F2430] text-zinc-300">
              <tr><td colspan="3" class="py-3.5 px-3 text-center text-zinc-500 italic">No stages executed yet</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <!-- Right Column (Metrics & Output) -->
    <section class="col-span-12 lg:col-span-7 flex flex-col gap-4">

      <!-- Metric Cards -->
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div class="bg-[#12151D] border border-[#1F2430] p-4 rounded-xl">
          <span class="text-xs font-medium uppercase tracking-wider text-zinc-400 block mb-1">Total Latency</span>
          <span id="metricLatency" class="text-2xl font-bold mono text-zinc-100">--</span>
        </div>
        <div class="bg-[#12151D] border border-[#1F2430] p-4 rounded-xl">
          <span class="text-xs font-medium uppercase tracking-wider text-zinc-400 block mb-1">Validation</span>
          <span id="metricValidation" class="text-xs font-semibold text-zinc-400 bg-zinc-800/40 px-2.5 py-1 rounded border border-zinc-700/40 inline-block mt-0.5">--</span>
        </div>
        <div class="bg-[#12151D] border border-[#1F2430] p-4 rounded-xl">
          <span class="text-xs font-medium uppercase tracking-wider text-zinc-400 block mb-1">Retries</span>
          <span id="metricRetries" class="text-2xl font-bold mono text-zinc-100">0</span>
        </div>
        <div class="bg-[#12151D] border border-[#1F2430] p-4 rounded-xl">
          <span class="text-xs font-medium uppercase tracking-wider text-zinc-400 block mb-1">Tables Used</span>
          <span id="metricTables" class="text-2xl font-bold mono text-zinc-100">--</span>
        </div>
      </div>

      <!-- Code & Log Console -->
      <div class="bg-[#12151D] border border-[#1F2430] rounded-xl overflow-hidden flex flex-col shadow-sm">

        <!-- Tabs Header -->
        <div class="flex items-center justify-between px-4 border-b border-[#1F2430] bg-[#141720]">
          <div class="flex gap-5">
            <button id="tab-sql" onclick="switchTab('sql')" class="py-3 text-sm font-semibold text-blue-400 border-b-2 border-blue-500 transition cursor-pointer">Generated SQL</button>
            <button id="tab-trace" onclick="switchTab('trace')" class="py-3 text-sm font-medium text-zinc-400 hover:text-zinc-200 border-b-2 border-transparent transition cursor-pointer">Validation & Self-Correction</button>
            <button id="tab-json" onclick="switchTab('json')" class="py-3 text-sm font-medium text-zinc-400 hover:text-zinc-200 border-b-2 border-transparent transition cursor-pointer">Raw JSON</button>
          </div>
          <button onclick="copyActiveContent()" class="text-xs font-medium text-zinc-400 hover:text-zinc-200 border border-[#242B3B] px-2.5 py-1 rounded-md bg-[#0B0D13] hover:bg-[#161A23] transition cursor-pointer flex items-center gap-1.5">
            <span id="copyIcon">📋</span> <span id="copyText">Copy</span>
          </button>
        </div>

        <!-- Terminal Output Viewers -->
        <div class="p-4 bg-[#090B10] mono text-sm text-zinc-300 min-h-[380px] max-h-[580px] overflow-auto leading-relaxed">

          <!-- View 1: Generated SQL -->
          <div id="view-sql">
            <p class="text-zinc-500 mb-2 font-sans text-xs">-- Output will appear here after execution</p>
            <pre id="outputSqlCode" class="text-emerald-400 whitespace-pre-wrap select-all font-mono text-sm leading-relaxed"></pre>
          </div>

          <!-- View 2: Validation Trace -->
          <div id="view-trace" class="hidden flex flex-col gap-3 font-sans">
            <p class="text-zinc-500 text-xs">-- Validation & Self-Correction Step Trace</p>
            <div id="traceCardsContainer" class="flex flex-col gap-2.5">
              <p class="text-zinc-500 italic text-xs">No validation steps recorded yet.</p>
            </div>
          </div>

          <!-- View 3: Raw JSON -->
          <div id="view-json" class="hidden">
            <pre id="outputRawJson" class="text-zinc-400 whitespace-pre-wrap font-mono text-xs leading-relaxed"></pre>
          </div>

        </div>
      </div>

    </section>
  </main>

  <script>
    let activeTab = 'sql';
    let lastResponseData = null;

    function setPreset(question) {
      document.getElementById('questionInput').value = question;
    }

    function switchTab(tab) {
      activeTab = tab;
      const tabs = ['sql', 'trace', 'json'];
      tabs.forEach(t => {
        const btn = document.getElementById('tab-' + t);
        const view = document.getElementById('view-' + t);
        if (t === tab) {
          btn.className = 'py-3 text-sm font-semibold text-blue-400 border-b-2 border-blue-500 transition cursor-pointer';
          view.classList.remove('hidden');
        } else {
          btn.className = 'py-3 text-sm font-medium text-zinc-400 hover:text-zinc-200 border-b-2 border-transparent transition cursor-pointer';
          view.classList.add('hidden');
        }
      });
    }

    function copyActiveContent() {
      let content = '';
      if (activeTab === 'sql') {
        content = document.getElementById('outputSqlCode').innerText;
      } else if (activeTab === 'trace') {
        content = (lastResponseData && lastResponseData.local && lastResponseData.local.validation_history_sql) || '';
      } else if (activeTab === 'json') {
        content = document.getElementById('outputRawJson').innerText;
      }
      if (!content) return;
      navigator.clipboard.writeText(content).then(() => {
        const copyText = document.getElementById('copyText');
        copyText.innerText = 'Copied!';
        setTimeout(() => { copyText.innerText = 'Copy'; }, 1500);
      });
    }

    async function runDebugFlow() {
      const question = document.getElementById('questionInput').value.trim();
      const layer = document.getElementById('layerSelect').value;
      const runBtn = document.getElementById('runBtn');
      const btnText = document.getElementById('btnText');
      const btnIcon = document.getElementById('btnIcon');

      if (!question) {
        alert('Please enter a natural language question.');
        return;
      }

      runBtn.disabled = true;
      btnIcon.innerText = '⏳';
      btnText.innerText = 'Executing Pipeline...';

      try {
        const response = await fetch('/internal/debug/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question: question, layer: layer, show_local_output: true })
        });
        const data = await response.json();
        lastResponseData = data;
        renderResults(data);
      } catch (err) {
        alert('Debug execution failed: ' + err.message);
      } finally {
        runBtn.disabled = false;
        btnIcon.innerText = '⚡';
        btnText.innerText = 'Execute Debug Run & Log Trace';
      }
    }

    function renderResults(data) {
      // 1. Metric Cards
      const latency = (data.metrics && data.metrics.total_latency_ms != null) ? (data.metrics.total_latency_ms / 1000).toFixed(2) + 's' : '--';
      document.getElementById('metricLatency').innerText = latency;

      const isPassed = data.status === 'passed';
      const valBadge = document.getElementById('metricValidation');
      if (isPassed) {
        valBadge.innerText = 'Passed';
        valBadge.className = 'text-xs font-semibold text-emerald-400 bg-emerald-950/40 px-2.5 py-1 rounded border border-emerald-800/40 inline-block mt-0.5';
      } else {
        valBadge.innerText = data.status || 'Failed';
        valBadge.className = 'text-xs font-semibold text-rose-400 bg-rose-950/40 px-2.5 py-1 rounded border border-rose-800/40 inline-block mt-0.5';
      }

      const attempts = (data.metrics && data.metrics.self_correction_attempts_used != null) 
        ? data.metrics.self_correction_attempts_used 
        : (data.local && data.local.attempts_used != null ? data.local.attempts_used : 0);
      document.getElementById('metricRetries').innerText = attempts;

      const tablesCount = (data.local && data.local.tables_count != null) ? data.local.tables_count : (data.tags && data.tags.tables_count != null ? data.tags.tables_count : null);
      const tablesList = (data.local && data.local.tables_used) ? data.local.tables_used : (data.tags && data.tags.tables ? data.tags.tables.split(', ') : []);
      
      const tablesElement = document.getElementById('metricTables');
      if (tablesCount != null && tablesCount > 0) {
        tablesElement.innerText = tablesCount + (tablesCount === 1 ? ' table' : ' tables');
        tablesElement.title = tablesList.join(', ');
      } else if (tablesList.length > 0 && tablesList[0] !== 'none') {
        tablesElement.innerText = tablesList.length + (tablesList.length === 1 ? ' table' : ' tables');
        tablesElement.title = tablesList.join(', ');
      } else {
        tablesElement.innerText = '--';
        tablesElement.title = '';
      }

      document.getElementById('stoppingBadge').innerText = data.stopping_point ? 'stopped at: ' + data.stopping_point : (isPassed ? 'complete' : 'failed');

      // 2. Stage Breakdown Table
      const stageBody = document.getElementById('stageTableBody');
      stageBody.innerHTML = '';
      const flow = (data.local && data.local.flow) || {};
      const stageOrder = ['request', 'retrieval', 'prompt', 'generation', 'validation', 'critic', 'correction', 'final'];
      const stages = Object.keys(flow).sort((a, b) => {
        const ia = stageOrder.indexOf(a);
        const ib = stageOrder.indexOf(b);
        return (ia !== -1 ? ia : 99) - (ib !== -1 ? ib : 99);
      });
      
      if (stages.length > 0) {
        stages.forEach(stg => {
          const item = flow[stg];
          if (!item) return;
          const tr = document.createElement('tr');
          let dur = '--';
          if (item.duration_ms != null && item.duration_ms !== 'unavailable') {
            dur = (item.duration_ms >= 1000) ? (item.duration_ms / 1000).toFixed(2) + 's' : item.duration_ms.toFixed(0) + 'ms';
          }
          let stColor = 'text-zinc-500';
          let statusText = item.status || 'not_executed';
          if (statusText === 'passed' || statusText === 'Success' || statusText === 'success') {
            stColor = 'text-emerald-400';
            statusText = 'Passed';
          } else if (statusText === 'failed' || statusText === 'Failed') {
            stColor = 'text-rose-400';
            statusText = 'Failed';
          } else if (statusText.startsWith('skipped')) {
            stColor = 'text-zinc-400 italic text-xs';
          } else if (statusText === 'executed' || statusText.startsWith('corrected')) {
            stColor = 'text-blue-400';
          }

          let stageLabel = stg.toUpperCase();
          if (stg === 'retrieval') stageLabel = '1. Semantic Retrieval';
          else if (stg === 'prompt') stageLabel = '2. Prompt Assembly';
          else if (stg === 'generation') stageLabel = '3. LLM SQL Generation';
          else if (stg === 'validation') stageLabel = '4. Deterministic Validation';
          else if (stg === 'critic') stageLabel = '5. LLM Critic Check';
          else if (stg === 'correction') stageLabel = '6. SQL Self-Correction';
          else if (stg === 'request') stageLabel = 'Total Request';
          else if (stg === 'final') stageLabel = 'Final Output';

          tr.innerHTML = `
            <td class="py-2.5 px-3 font-medium text-zinc-200">${stageLabel}</td>
            <td class="py-2.5 px-3 font-medium ${stColor}">${statusText}</td>
            <td class="py-2.5 px-3 text-right mono font-medium text-zinc-400">${dur}</td>
          `;
          stageBody.appendChild(tr);
        });
      } else {
        stageBody.innerHTML = '<tr><td colspan="3" class="py-3.5 px-3 text-center text-zinc-500 italic">No stage timing available</td></tr>';
      }

      // 3. Generated SQL Tab
      const finalSql = (data.local && (data.local.final_sql || data.local.generation)) || '-- No SQL generated';
      document.getElementById('outputSqlCode').innerText = finalSql;

      // 4. Validation & Self-Correction Steps Tab
      const traceContainer = document.getElementById('traceCardsContainer');
      traceContainer.innerHTML = '';
      const events = (data.local && (data.local.production_trace_events || data.local.validation_history)) || [];
      if (events.length > 0) {
        events.forEach((step, idx) => {
          const card = document.createElement('div');
          card.className = 'border border-[#1F2430] bg-[#12151D] rounded-xl p-4 text-xs sm:text-sm flex flex-col gap-3 shadow-sm';
          
          let title = '';
          let badge = '';
          let sql = step.sql || step.correctedSql || '';
          let issues = step.deterministicIssues || step.issues || [];
          let criticIssues = step.verifiedCriticIssues || [];
          let allIssues = [...issues, ...criticIssues];

          if (step.event === 'initial_generation') {
            title = 'Step 1: Initial LLM Candidate Generation';
            badge = '<span class="text-blue-400 bg-blue-950/40 px-2.5 py-0.5 rounded border border-blue-800/40 font-semibold text-xs">Initial Candidate</span>';
          } else if (step.event === 'final_result') {
            title = 'Final Step: Production Execution SQL';
            badge = step.status === 'passed' 
              ? '<span class="text-emerald-400 bg-emerald-950/40 px-2.5 py-0.5 rounded border border-emerald-800/40 font-semibold text-xs">Validated & Ready</span>'
              : '<span class="text-rose-400 bg-rose-950/40 px-2.5 py-0.5 rounded border border-rose-800/40 font-semibold text-xs">Failed</span>';
          } else if (step.attempt != null) {
            title = `Step ${idx + 1}: Deterministic & Schema Validation (Attempt ${step.attempt})`;
            if (step.action === 'passed' || step.status === 'passed') {
              badge = '<span class="text-emerald-400 bg-emerald-950/40 px-2.5 py-0.5 rounded border border-emerald-800/40 font-semibold text-xs">Validation Passed (0 issues)</span>';
            } else {
              badge = `<span class="text-amber-400 bg-amber-950/40 px-2.5 py-0.5 rounded border border-amber-800/40 font-semibold text-xs">Correction Required (${allIssues.length} issues)</span>`;
            }
          } else if (step.event === 'after_correction') {
            title = `Step ${idx + 1}: Self-Correction Applied (Attempt ${step.attempt + 1})`;
            badge = '<span class="text-purple-400 bg-purple-950/40 px-2.5 py-0.5 rounded border border-purple-800/40 font-semibold text-xs">Corrected SQL</span>';
          } else {
            title = `Step ${idx + 1}: ${step.event || 'Validation Event'}`;
            badge = '<span class="text-zinc-400 bg-zinc-800/40 px-2.5 py-0.5 rounded border border-zinc-700/40 font-semibold text-xs">Info</span>';
          }

          let bodyHtml = `
            <div class="flex items-center justify-between">
              <span class="font-bold text-zinc-200 text-sm">${title}</span>
              ${badge}
            </div>
          `;

          if (sql) {
            bodyHtml += `<pre class="bg-[#090B10] p-3 rounded-lg text-emerald-400 whitespace-pre-wrap border border-[#1F2430] font-mono text-xs sm:text-sm leading-relaxed select-all">${sql}</pre>`;
          }

          if (allIssues.length > 0) {
            bodyHtml += `
              <div class="bg-rose-950/20 border border-rose-900/40 rounded-lg p-3 text-rose-300 text-xs sm:text-sm">
                <div class="font-bold mb-1.5">Issues Identified:</div>
                <ul class="list-disc list-inside space-y-1">
                  ${allIssues.map(i => `<li>${i}</li>`).join('')}
                </ul>
              </div>
            `;
          } else if (step.attempt != null && (step.action === 'passed' || step.status === 'passed')) {
            bodyHtml += `
              <div class="text-emerald-400/90 flex items-center gap-2 text-xs bg-emerald-950/20 border border-emerald-900/30 rounded-lg p-2.5">
                <span>✓</span> Syntax valid, physical schema confirmed, relationships & RLS verified. No corrections needed.
              </div>
            `;
          }

          card.innerHTML = bodyHtml;
          traceContainer.appendChild(card);
        });
      } else {
        traceContainer.innerHTML = '<p class="text-zinc-500 italic text-xs">No validation steps recorded.</p>';
      }

      // 5. Raw JSON Tab
      document.getElementById('outputRawJson').innerText = JSON.stringify(data, null, 2);
    }
  </script>
</body>
</html>
"""


@router.post("/run")
def run_debug(request: DebugRunRequest) -> dict[str, Any]:
    """Execute real production components for the given question up to the specified layer."""
    if request.layer not in LAYERS:
        raise HTTPException(status_code=400, detail=f"Unknown layer '{request.layer}'. Choose one of: {', '.join(LAYERS)}.")
    try:
        result = DebugRunner().run(question=request.question, layer=request.layer)
        return {
            "requested_layer": result.requested_layer,
            "prerequisites_executed": result.prerequisites,
            "stopping_point": result.stopping_point,
            "layers_not_executed": [x for x in LAYERS if x not in {*result.prerequisites, result.requested_layer}],
            "status": result.status,
            "metrics": result.metrics,
            "tags": result.tags,
            "local": result.local if request.show_local_output else {},
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Debug execution failed: {type(exc).__name__}") from exc


@router.get("/ui", response_class=HTMLResponse)
def debug_ui() -> HTMLResponse:
    """Serve the lightweight single-page Developer Debugger UI."""
    return HTMLResponse(content=_DEBUG_UI_HTML)
