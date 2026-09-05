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
                <th class="py-2.5 px-3 font-semibold">Stage & Operation</th>
                <th class="py-2.5 px-3 font-semibold">Status</th>
                <th class="py-2.5 px-3 font-semibold text-right">Total Duration</th>
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
            <button id="tab-latency" onclick="switchTab('latency')" class="py-3 text-sm font-medium text-zinc-400 hover:text-zinc-200 border-b-2 border-transparent transition cursor-pointer flex items-center gap-1.5"><span>⏱️</span> Latency Hierarchy</button>
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

          <!-- View 3: Hierarchical Latency -->
          <div id="view-latency" class="hidden flex flex-col gap-4 font-sans">
            <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
              <div class="bg-[#12151D] border border-[#1F2430] p-2.5 rounded-lg">
                <span class="text-zinc-400 block text-[10px] uppercase">Total Request</span>
                <span id="latencyTotal" class="font-mono font-bold text-zinc-100 text-sm">--</span>
              </div>
              <div class="bg-[#12151D] border border-[#1F2430] p-2.5 rounded-lg">
                <span class="text-zinc-400 block text-[10px] uppercase">Pipeline Time</span>
                <span id="latencyPipeline" class="font-mono font-bold text-blue-400 text-sm">--</span>
              </div>
              <div class="bg-[#12151D] border border-[#1F2430] p-2.5 rounded-lg">
                <span class="text-zinc-400 block text-[10px] uppercase">API Overhead</span>
                <span id="latencyOverhead" class="font-mono font-bold text-amber-400 text-sm">--</span>
              </div>
              <div class="bg-[#12151D] border border-[#1F2430] p-2.5 rounded-lg">
                <span class="text-zinc-400 block text-[10px] uppercase">Orchestration Gaps</span>
                <span id="latencyGaps" class="font-mono font-bold text-emerald-400 text-sm">--</span>
              </div>
            </div>

            <!-- Detailed Latency Hierarchy Table -->
            <div class="bg-[#12151D] border border-[#1F2430] rounded-xl p-4 flex flex-col gap-3 shadow-sm">
              <div class="flex items-center justify-between">
                <h3 class="text-xs font-bold uppercase tracking-wider text-zinc-300">Detailed Latency Hierarchy Table</h3>
                <span class="text-[11px] font-sans text-zinc-500">All Operations & Sub-Steps (Inclusive vs. Exclusive)</span>
              </div>
              <div class="overflow-x-auto rounded-lg border border-[#1F2430]">
                <table class="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr class="bg-[#141720] text-zinc-400 border-b border-[#1F2430]">
                      <th class="py-2.5 px-3 font-semibold">Stage / Sub-Operation</th>
                      <th class="py-2.5 px-3 font-semibold">Type & Notes</th>
                      <th class="py-2.5 px-3 font-semibold text-right">Inclusive</th>
                      <th class="py-2.5 px-3 font-semibold text-right">Exclusive (Self)</th>
                      <th class="py-2.5 px-3 font-semibold text-right">Gaps / Overhead</th>
                    </tr>
                  </thead>
                  <tbody id="detailedLatencyTableBody" class="divide-y divide-[#1F2430] font-mono text-zinc-300">
                    <tr><td colspan="5" class="py-3 px-3 text-center text-zinc-500 italic font-sans">No execution data available</td></tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div class="bg-[#0A0C11] border border-[#1F2430] rounded-lg p-4 font-mono text-xs leading-relaxed overflow-x-auto">
              <div class="flex items-center justify-between mb-2">
                <div class="flex items-center gap-2">
                  <span class="text-zinc-300 font-sans text-xs font-semibold">Execution Latency Tree</span>
                  <span class="text-zinc-500 font-sans text-[11px]" id="treeModeLabel">(Concise View)</span>
                </div>
                <div class="flex items-center gap-1.5">
                  <div class="inline-flex rounded-lg border border-[#1F2430] bg-[#12151D] p-0.5">
                    <button id="btnTreeModeConcise" onclick="setTreeMode('concise')" class="px-2.5 py-0.5 rounded text-[11px] font-sans font-medium bg-blue-600/30 text-blue-300 border border-blue-500/40 cursor-pointer">Concise</button>
                    <button id="btnTreeModeFull" onclick="setTreeMode('full')" class="px-2.5 py-0.5 rounded text-[11px] font-sans font-medium bg-transparent text-zinc-400 hover:text-zinc-200 cursor-pointer">Full Details</button>
                  </div>
                  <span id="latencyAuditBadge" class="text-[11px] font-mono text-zinc-500 ml-2"></span>
                </div>
              </div>
              <pre id="outputLatencyTree" class="text-zinc-300 font-mono text-xs select-all whitespace-pre leading-loose">-- Run execution to display hierarchical latency tree</pre>
            </div>

            <!-- Quick Reference Legend -->
            <div class="border border-[#1F2430] bg-[#12151D] rounded-lg p-3 text-xs flex flex-col gap-2">
              <span class="text-[11px] font-bold uppercase tracking-wider text-zinc-400">Latency Descriptors Reference</span>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5 text-[11px] text-zinc-400">
                <div><span class="font-semibold text-zinc-200">End-to-End Request:</span> Full HTTP cycle</div>
                <div><span class="font-semibold text-zinc-200">Core AI Pipeline:</span> Pure AI execution time</div>
                <div><span class="font-semibold text-zinc-200">API Framework Overhead:</span> FastAPI routing & serialization</div>
                <div><span class="font-semibold text-zinc-200">Semantic Context Retrieval:</span> Vector & metadata search</div>
                <div><span class="font-semibold text-zinc-200">Prompt Template Assembly:</span> Prompt construction & rules</div>
                <div><span class="font-semibold text-zinc-200">LLM SQL Generation:</span> Model inference & SQL build</div>
                <div><span class="font-semibold text-zinc-200">Model VRAM Load:</span> Model load (cold vs warm)</div>
                <div><span class="font-semibold text-zinc-200">Prompt Eval (TTFT):</span> Prompt ingestion to first token</div>
                <div><span class="font-semibold text-zinc-200">Token Generation:</span> Autoregressive SQL token production</div>
                <div><span class="font-semibold text-zinc-200">Deterministic SQL Validation:</span> Syntax, schema & RLS rules</div>
                <div><span class="font-semibold text-zinc-200">LLM Semantic Review:</span> SQL Critic logic validation</div>
                <div><span class="font-semibold text-zinc-200">Self-Correction Repair:</span> Automated iterative SQL repair</div>
              </div>
            </div>
          </div>

          <!-- View 4: Raw JSON -->
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

    function formatMs(val) {
      if (val == null || val === 'unavailable') return '--';
      const num = Number(val);
      if (isNaN(num)) return String(val);
      return (num >= 1000) ? (num / 1000).toFixed(2) + 's' : num.toFixed(1) + 'ms';
    }

    const NODE_DESCRIPTORS = {
      'request_lifecycle': 'End-to-End Request',
      'request': 'End-to-End Request',
      'pipeline': 'Core AI Pipeline',
      'preflight': 'Preflight Safety Checks',
      'input_checks': 'Read-Only Safety Check',
      'table_checks': 'Physical Table Check',
      'context_retrieval': 'Semantic Context Retrieval',
      'candidate_planning': 'Candidate Table Planning',
      'retrieval': 'Semantic Retrieval Search',
      'query_embedding': 'Vector Query Embedding',
      'vector_search': 'Vector Embedding Search',
      'relevance_filtering_and_planning': 'Table Relevance Pruning',
      'context_assembly': 'Schema Context Assembly',
      'prompt': 'Prompt Template Assembly',
      'prompt_construction': 'Prompt Template Assembly',
      'sql_generation': 'LLM SQL Generation',
      'llm_inference': 'LLM Model Inference',
      'ollama_generation': 'Ollama Engine Execution',
      'output_parsing': 'JSON Response Parsing',
      'deterministic_validation': 'Deterministic SQL Validation',
      'syntax': 'SQL Syntax Parsing',
      'schema': 'Table & Column Confirmation',
      'relationship': 'JOIN Safety Validation',
      'rls': 'RLS Tenant Security',
      'deterministic_validation_syntax': 'SQL Syntax Parsing',
      'deterministic_validation_schema': 'Table & Column Confirmation',
      'deterministic_validation_relationship': 'JOIN Safety Validation',
      'deterministic_validation_rls': 'RLS Tenant Security',
      'deterministic_repair': 'Deterministic SQL Repair',
      'self_correction': 'Self-Correction Repair',
      'critic': 'LLM Semantic Review',
      'critic_context': 'Review Context Assembly',
      'critic_evaluation': 'Semantic Query Critique',
      'critic_verifier': 'Defect Fact Verification',
      'correction_prep': 'Error Feedback Assembly',
      'correction_llm': 'SQL Repair Generation',
      'correction_attempt_1': 'Correction Attempt 1',
      'correction_attempt_2': 'Correction Attempt 2',
      'correction_attempt_3': 'Correction Attempt 3',
      'sql_critic': 'LLM Semantic Review',
      'sql_correction_llm': 'SQL Repair Generation',
    };

    let currentTreeMode = 'concise';

    function setTreeMode(mode) {
      currentTreeMode = mode;
      const btnConcise = document.getElementById('btnTreeModeConcise');
      const btnFull = document.getElementById('btnTreeModeFull');
      const modeLabel = document.getElementById('treeModeLabel');
      if (btnConcise && btnFull) {
        if (mode === 'concise') {
          btnConcise.className = 'px-2.5 py-0.5 rounded text-[11px] font-sans font-medium bg-blue-600/30 text-blue-300 border border-blue-500/40 cursor-pointer';
          btnFull.className = 'px-2.5 py-0.5 rounded text-[11px] font-sans font-medium bg-transparent text-zinc-400 hover:text-zinc-200 cursor-pointer';
          if (modeLabel) modeLabel.innerText = '(Concise View)';
        } else {
          btnFull.className = 'px-2.5 py-0.5 rounded text-[11px] font-sans font-medium bg-blue-600/30 text-blue-300 border border-blue-500/40 cursor-pointer';
          btnConcise.className = 'px-2.5 py-0.5 rounded text-[11px] font-sans font-medium bg-transparent text-zinc-400 hover:text-zinc-200 cursor-pointer';
          if (modeLabel) modeLabel.innerText = '(Full Details)';
        }
      }
      if (lastResponseData) {
        const summary = (lastResponseData.local && lastResponseData.local.latency_summary) || null;
        const hierarchy = (lastResponseData.local && lastResponseData.local.latency_hierarchy) || (summary && summary.hierarchy) || null;
        if (hierarchy && hierarchy.name) {
          document.getElementById('outputLatencyTree').innerText = renderLatencyNode(hierarchy, '', true, true, currentTreeMode);
        }
      }
    }

    function renderLatencyNode(node, prefix = '', isLast = true, isRoot = true, mode = currentTreeMode) {
      if (!node || !node.name) return '';
      const branch = isRoot ? '' : (isLast ? '└── ' : '├── ');
      const dur = (node.inclusive_duration_ms != null) ? formatMs(node.inclusive_duration_ms) : '--';

      const opKey = node.operation || node.name;
      const descriptor = NODE_DESCRIPTORS[opKey] || NODE_DESCRIPTORS[node.name] || opKey;

      if (mode === 'concise') {
        let displayTitle = descriptor;
        let line = `${prefix}${branch}${displayTitle} [${dur}]\n`;
        const nextPrefix = isRoot ? '' : prefix + (isLast ? '    ' : '│   ');

        // In concise mode, skip repetitive leaf micro-spans already shown in the detailed table:
        // - deterministic_validation sub-rules (syntax, schema, relationship, rls)
        // - duplicate llm_inference child under sql_generation
        // - duplicate sql_critic child under critic_evaluation
        const children = (node.children || []).filter(c => {
          const cOp = c.operation || c.name;
          if (cOp && cOp.startsWith('deterministic_validation_')) return false;
          if (cOp === 'llm_inference' && (node.operation === 'sql_generation' || node.name === 'sql_generation')) return false;
          if (cOp === 'sql_critic' && (node.operation === 'critic_evaluation' || node.name === 'critic_evaluation')) return false;
          return true;
        });

        children.forEach((child, idx) => {
          line += renderLatencyNode(child, nextPrefix, idx === children.length - 1, false, mode);
        });
        return line;
      }

      // Full mode
      const excl = (node.exclusive_duration_ms != null) ? ` (self: ${formatMs(node.exclusive_duration_ms)})` : '';
      const gaps = (node.orchestration_gaps_ms != null && node.orchestration_gaps_ms > 0) ? ` [gaps: ${formatMs(node.orchestration_gaps_ms)}]` : '';
      const unaccounted = (node.unaccounted_ms != null && node.unaccounted_ms > 0.05) ? ` [unaccounted: ${formatMs(node.unaccounted_ms)}]` : '';

      let displayTitle = descriptor;
      if (node.operation && node.operation !== node.name && node.name) {
        displayTitle = `${descriptor} (${node.operation})`;
      } else if (descriptor !== node.name) {
        displayTitle = `${descriptor} (${node.name})`;
      }

      let extra = '';
      if (node.metadata) {
        if (node.metadata.model_load_type) {
          extra += ` [load: ${node.metadata.model_load_type}]`;
        }
        if (node.metadata.server_duration_ms != null) {
          extra += ` [server: ${formatMs(node.metadata.server_duration_ms)}]`;
        }
        if (node.metadata.client_overhead_ms != null && node.metadata.client_overhead_ms > 0) {
          extra += ` [overhead: ${formatMs(node.metadata.client_overhead_ms)}]`;
        }
      }

      let line = `${prefix}${branch}${displayTitle} [${dur}]${excl}${gaps}${unaccounted}${extra}\n`;
      const nextPrefix = isRoot ? '' : prefix + (isLast ? '    ' : '│   ');

      // Render nested Ollama metrics if present on this node in full mode
      if (node.metadata && node.metadata.eval_duration_ms != null) {
        if (node.metadata.load_duration_ms != null && node.metadata.load_duration_ms > 0) {
          const loadType = node.metadata.model_load_type ? ` [${node.metadata.model_load_type}]` : '';
          line += `${nextPrefix}├── Model VRAM Load [${formatMs(node.metadata.load_duration_ms)}]${loadType}\n`;
        }
        if (node.metadata.prompt_eval_duration_ms != null) {
          const tps = node.metadata.prompt_tps ? ` (${node.metadata.prompt_tps} tps)` : '';
          line += `${nextPrefix}├── Prompt Eval (TTFT) [${formatMs(node.metadata.prompt_eval_duration_ms)}]${tps}\n`;
        }
        if (node.metadata.eval_duration_ms != null) {
          const tps = node.metadata.generation_tps ? ` (${node.metadata.generation_tps} tps)` : '';
          line += `${nextPrefix}├── Token Generation [${formatMs(node.metadata.eval_duration_ms)}]${tps}\n`;
        }
        if (node.metadata.client_overhead_ms != null && node.metadata.client_overhead_ms > 0) {
          line += `${nextPrefix}└── Client HTTP Overhead [${formatMs(node.metadata.client_overhead_ms)}]\n`;
        }
      }

      const children = node.children || [];
      children.forEach((child, idx) => {
        line += renderLatencyNode(child, nextPrefix, idx === children.length - 1, false, mode);
      });
      return line;
    }

    function renderLatencyTableRows(node, depth = 0) {
      if (!node || !node.name) return [];
      const rows = [];
      const indent = depth > 0 ? '&nbsp;'.repeat(depth * 3) + '↳ ' : '';
      const opKey = node.operation || node.name;
      const descriptor = NODE_DESCRIPTORS[opKey] || NODE_DESCRIPTORS[node.name] || opKey;
      const nameLabel = (node.name && node.operation && node.name !== node.operation)
        ? `${descriptor} <span class="text-zinc-500 font-normal">(${node.operation})</span>`
        : (descriptor !== node.name ? `${descriptor} <span class="text-zinc-500 font-normal">(${node.name})</span>` : descriptor);

      const incStr = (node.inclusive_duration_ms != null) ? formatMs(node.inclusive_duration_ms) : '--';
      const exclStr = (node.exclusive_duration_ms != null) ? formatMs(node.exclusive_duration_ms) : '--';
      
      let gapsNotes = '--';
      if (node.orchestration_gaps_ms != null && node.orchestration_gaps_ms > 0) {
        gapsNotes = `gaps: ${formatMs(node.orchestration_gaps_ms)}`;
      } else if (node.unaccounted_ms != null && node.unaccounted_ms > 0.05) {
        gapsNotes = `unacc: ${formatMs(node.unaccounted_ms)}`;
      }

      let typeNotes = '<span class="text-zinc-500 font-sans text-[11px]">stage</span>';
      if (node.is_leaf) {
        typeNotes = '<span class="text-blue-400 font-sans text-[11px]">leaf operation</span>';
      }
      if (node.metadata) {
        if (node.metadata.model_load_type) {
          typeNotes = `<span class="text-amber-400 font-mono text-[11px]">${node.metadata.model_load_type} load</span>`;
        }
      }

      const bgClass = depth === 0 ? 'bg-[#151923] font-bold text-zinc-100' : (depth === 1 ? 'bg-[#10141D] font-semibold text-zinc-200' : 'text-zinc-300 hover:bg-[#151922]/50');

      rows.push(`
        <tr class="${bgClass} border-b border-[#1A1F2C]">
          <td class="py-2 px-3 font-sans">${indent}<span class="font-mono text-xs">${nameLabel}</span></td>
          <td class="py-2 px-3 font-mono text-[11px]">${typeNotes}</td>
          <td class="py-2 px-3 text-right mono text-emerald-400 font-medium">${incStr}</td>
          <td class="py-2 px-3 text-right mono text-zinc-400">${exclStr}</td>
          <td class="py-2 px-3 text-right mono text-zinc-500 text-[11px]">${gapsNotes}</td>
        </tr>
      `);

      // If node has Ollama breakdown in metadata:
      if (node.metadata && node.metadata.eval_duration_ms != null) {
        const subIndent = '&nbsp;'.repeat((depth + 1) * 3) + '↳ ';
        if (node.metadata.load_duration_ms != null && node.metadata.load_duration_ms > 0) {
          const loadType = node.metadata.model_load_type ? `${node.metadata.model_load_type} load` : 'vram load';
          rows.push(`
            <tr class="bg-[#0B0D13]/60 text-xs border-b border-[#1A1F2C]">
              <td class="py-1.5 px-3 font-sans">${subIndent}<span class="text-zinc-300 font-medium font-mono">Model VRAM Load</span></td>
              <td class="py-1.5 px-3 font-mono text-[11px] text-amber-400">${loadType}</td>
              <td class="py-1.5 px-3 text-right mono text-amber-400">${formatMs(node.metadata.load_duration_ms)}</td>
              <td class="py-1.5 px-3 text-right mono text-zinc-600">--</td>
              <td class="py-1.5 px-3 text-right mono text-zinc-600">--</td>
            </tr>
          `);
        }
        if (node.metadata.prompt_eval_duration_ms != null) {
          const tps = node.metadata.prompt_tps ? `${node.metadata.prompt_tps} tps` : 'TTFT';
          rows.push(`
            <tr class="bg-[#0B0D13]/60 text-xs border-b border-[#1A1F2C]">
              <td class="py-1.5 px-3 font-sans">${subIndent}<span class="text-zinc-300 font-medium font-mono">Prompt Eval (TTFT)</span></td>
              <td class="py-1.5 px-3 font-mono text-[11px] text-zinc-400">${tps}</td>
              <td class="py-1.5 px-3 text-right mono text-blue-400">${formatMs(node.metadata.prompt_eval_duration_ms)}</td>
              <td class="py-1.5 px-3 text-right mono text-zinc-600">--</td>
              <td class="py-1.5 px-3 text-right mono text-zinc-600">--</td>
            </tr>
          `);
        }
        if (node.metadata.eval_duration_ms != null) {
          const tps = node.metadata.generation_tps ? `${node.metadata.generation_tps} tps` : 'Tokens';
          rows.push(`
            <tr class="bg-[#0B0D13]/60 text-xs border-b border-[#1A1F2C]">
              <td class="py-1.5 px-3 font-sans">${subIndent}<span class="text-zinc-300 font-medium font-mono">Token Generation</span></td>
              <td class="py-1.5 px-3 font-mono text-[11px] text-zinc-400">${tps}</td>
              <td class="py-1.5 px-3 text-right mono text-purple-400">${formatMs(node.metadata.eval_duration_ms)}</td>
              <td class="py-1.5 px-3 text-right mono text-zinc-600">--</td>
              <td class="py-1.5 px-3 text-right mono text-zinc-600">--</td>
            </tr>
          `);
        }
        if (node.metadata.client_overhead_ms != null && node.metadata.client_overhead_ms > 0) {
          rows.push(`
            <tr class="bg-[#0B0D13]/60 text-xs border-b border-[#1A1F2C]">
              <td class="py-1.5 px-3 font-sans">${subIndent}<span class="text-zinc-400 font-medium font-mono">Client HTTP Overhead</span></td>
              <td class="py-1.5 px-3 font-mono text-[11px] text-zinc-500">network</td>
              <td class="py-1.5 px-3 text-right mono text-zinc-400">${formatMs(node.metadata.client_overhead_ms)}</td>
              <td class="py-1.5 px-3 text-right mono text-zinc-600">--</td>
              <td class="py-1.5 px-3 text-right mono text-zinc-600">--</td>
            </tr>
          `);
        }
      }

      const children = node.children || [];
      children.forEach(child => {
        rows.push(...renderLatencyTableRows(child, depth + 1));
      });
      return rows;
    }

    function setPreset(question) {
      document.getElementById('questionInput').value = question;
    }

    function switchTab(tab) {
      activeTab = tab;
      const tabs = ['sql', 'trace', 'latency', 'json'];
      tabs.forEach(t => {
        const btn = document.getElementById('tab-' + t);
        const view = document.getElementById('view-' + t);
        if (btn && view) {
          if (t === tab) {
            btn.className = 'py-3 text-sm font-semibold text-blue-400 border-b-2 border-blue-500 transition cursor-pointer flex items-center gap-1.5';
            view.classList.remove('hidden');
          } else {
            btn.className = 'py-3 text-sm font-medium text-zinc-400 hover:text-zinc-200 border-b-2 border-transparent transition cursor-pointer flex items-center gap-1.5';
            view.classList.add('hidden');
          }
        }
      });
    }

    function copyActiveContent() {
      let content = '';
      if (activeTab === 'sql') {
        content = document.getElementById('outputSqlCode').innerText;
      } else if (activeTab === 'trace') {
        content = (lastResponseData && lastResponseData.local && lastResponseData.local.validation_history_sql) || '';
      } else if (activeTab === 'latency') {
        content = (document.getElementById('outputLatencyTree') && document.getElementById('outputLatencyTree').innerText) || '';
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

      // 2. Stage Breakdown Table (Inclusive & Exclusive)
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
          const incVal = (item.inclusive_duration_ms != null && item.inclusive_duration_ms !== 'unavailable') ? item.inclusive_duration_ms : item.duration_ms;
          let durStr = '--';
          if (incVal != null && incVal !== 'unavailable') {
            durStr = (incVal >= 1000) ? (incVal / 1000).toFixed(2) + 's' : Number(incVal).toFixed(1) + 'ms';
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
          let descriptor = item.descriptor || '';
          if (stg === 'retrieval') {
            stageLabel = '1. Semantic Retrieval';
            descriptor = descriptor || 'Semantic Context Retrieval';
          } else if (stg === 'prompt') {
            stageLabel = '2. Prompt Assembly';
            descriptor = descriptor || 'Prompt Template Assembly';
          } else if (stg === 'generation') {
            stageLabel = '3. LLM SQL Generation';
            descriptor = descriptor || 'LLM SQL Generation';
          } else if (stg === 'validation') {
            stageLabel = '4. Deterministic Validation';
            descriptor = descriptor || 'Deterministic SQL Validation';
          } else if (stg === 'critic') {
            stageLabel = '5. LLM Critic Check';
            descriptor = descriptor || 'LLM Semantic Review';
          } else if (stg === 'correction') {
            stageLabel = '6. SQL Self-Correction';
            descriptor = descriptor || 'Self-Correction Repair';
          } else if (stg === 'request') {
            stageLabel = 'Total Request';
            descriptor = descriptor || 'End-to-End Request';
          } else if (stg === 'final') {
            stageLabel = 'Final Output';
            descriptor = descriptor || 'Final Output Delivery';
          }

          tr.innerHTML = `
            <td class="py-2.5 px-3">
              <div class="font-semibold text-zinc-100">${stageLabel}</div>
              <div class="text-[11px] text-zinc-400 font-normal">${descriptor}</div>
            </td>
            <td class="py-2.5 px-3 font-medium ${stColor}">${statusText}</td>
            <td class="py-2.5 px-3 text-right mono font-medium text-zinc-200">${durStr}</td>
          `;
          stageBody.appendChild(tr);
        });
      } else {
        stageBody.innerHTML = '<tr><td colspan="3" class="py-3.5 px-3 text-center text-zinc-500 italic">No stage timing available</td></tr>';
      }

      // Latency Hierarchy Tab
      const summary = (data.local && data.local.latency_summary) || null;
      const hierarchy = (data.local && data.local.latency_hierarchy) || (summary && summary.hierarchy) || null;
      if (summary) {
        document.getElementById('latencyTotal').innerText = formatMs(summary.total_duration_ms);
        document.getElementById('latencyPipeline').innerText = formatMs(summary.pipeline_duration_ms);
        document.getElementById('latencyOverhead').innerText = formatMs(summary.api_framework_overhead_ms);
        const gaps = summary.orchestration_gaps_ms != null ? summary.orchestration_gaps_ms : 0.0;
        document.getElementById('latencyGaps').innerText = formatMs(gaps);
        if (summary.request_id) {
          document.getElementById('latencyAuditBadge').innerText = 'Req: ' + summary.request_id.slice(0, 8);
        }
      } else {
        const reqDur = (data.metrics && data.metrics.total_latency_ms) || (data.metrics && data.metrics.request_latency_ms) || null;
        document.getElementById('latencyTotal').innerText = reqDur ? formatMs(reqDur) : '--';
        document.getElementById('latencyPipeline').innerText = '--';
        document.getElementById('latencyOverhead').innerText = '--';
        document.getElementById('latencyGaps').innerText = '--';
      }

      const detailedTableBody = document.getElementById('detailedLatencyTableBody');
      if (detailedTableBody) {
        if (hierarchy && hierarchy.name) {
          const rows = renderLatencyTableRows(hierarchy, 0);
          detailedTableBody.innerHTML = rows.join('');
        } else {
          detailedTableBody.innerHTML = '<tr><td colspan="5" class="py-3 px-3 text-center text-zinc-500 italic font-sans">No hierarchical span trace recorded for this layer execution.</td></tr>';
        }
      }

      if (hierarchy && hierarchy.name) {
        document.getElementById('outputLatencyTree').innerText = renderLatencyNode(hierarchy);
      } else {
        document.getElementById('outputLatencyTree').innerText = '-- No hierarchical span trace recorded for this layer execution.';
      }

      // 3. Generated SQL Tab
      let finalSql = (data.local && data.local.final_sql) || '';
      if (!finalSql || data.status === 'failed') {
        const reason = (data.local && (data.local.failure_reason || (data.local.issues && data.local.issues.join('; ')))) || 'Validation failed: No valid SQL produced.';
        finalSql = `-- ❌ FAILED: No executable SQL produced\n-- Reason: ${reason}`;
      }
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

          if (step.criticStatus || step.criticExecuted) {
            const criticDur = step.criticDurationMs != null ? (step.criticDurationMs >= 1000 ? (step.criticDurationMs / 1000).toFixed(2) + 's' : step.criticDurationMs.toFixed(0) + 'ms') : '--';
            const criticStatus = step.criticStatus || 'PASS';
            const verifiedCount = (step.verifiedCriticIssues || []).length;
            const criticBadge = criticStatus === 'PASS' 
              ? '<span class="text-emerald-400 font-mono text-xs font-semibold">✓ Pass</span>' 
              : (verifiedCount === 0 
                  ? '<span class="text-blue-400 font-mono text-xs font-medium">Advisory (0 verified defects)</span>' 
                  : `<span class="text-amber-400 font-mono text-xs font-medium">⚠️ ${verifiedCount} defects confirmed</span>`);
            
            bodyHtml += `
              <div class="flex items-center justify-between text-xs bg-[#0E1118] border border-[#1F2430] rounded-lg px-3 py-2 text-zinc-300">
                <span class="flex items-center gap-2">
                  <span>🧠</span>
                  <span><strong>LLM Critic Check</strong> (model response: <code class="text-zinc-200">${criticStatus}</code>)</span>
                </span>
                <div class="flex items-center gap-3">
                  ${criticBadge}
                  <span class="mono text-zinc-400">${criticDur}</span>
                </div>
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
