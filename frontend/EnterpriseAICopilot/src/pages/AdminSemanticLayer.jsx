import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AdminSidebar from "../components/AdminSidebar";
import AdminTopBar from "../components/AdminTopBar";
import {
  IconBookOpen,
  IconCheck,
  IconDatabase,
  IconFileText,
  IconLayers,
  IconLoader,
  IconTable,
  IconX,
} from "../components/icons";
import {
  generateSemanticDraft,
  getSemanticLayerStatus,
  uploadSemanticSources,
} from "../services/semanticLayerService";
import "../styles/admin.css";
import "../styles/admin-pages.css";
import "../styles/semantic-layer.css";

const SOURCE_FIELDS = [
  {
    key: "schema",
    label: "Schema definition",
    type: "SQL, PDF, or JSON",
    accept: ".sql,.pdf,.json",
    required: true,
    Icon: IconLayers,
  },
  {
    key: "documentation",
    label: "Documentation",
    type: "Optional supporting documentation",
    Icon: IconBookOpen,
  },
  {
    key: "glossary",
    label: "Business glossary",
    type: "Optional business terminology",
    Icon: IconTable,
  },
  {
    key: "sampleData",
    label: "Sample data",
    type: "Optional CSV sample",
    accept: ".csv",
    Icon: IconDatabase,
  },
];
const EMPTY_FILES = {
  schema: null,
  documentation: null,
  glossary: null,
  sampleData: null,
};

function formatTimestamp(value) {
  const date = new Date(value);
  return value && !Number.isNaN(date.getTime())
    ? date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" })
    : "Not available";
}
function sourceCount(sources) {
  return Object.values(sources || {}).filter(Boolean).length;
}
function validateUpload({ name, description, files }) {
  const errors = {};
  if (!name.trim()) errors.name = "Enter a name for this data source.";
  else if (name.trim().length > 100)
    errors.name = "Use a name with 100 characters or fewer.";
  if (!description.trim())
    errors.description = "Add a short description for this data source.";
  else if (description.trim().length > 500)
    errors.description = "Use a description with 500 characters or fewer.";
  if (!files.schema) errors.schema = "Choose the schema file to continue.";
  else if (!/\.(sql|pdf|json)$/i.test(files.schema.name))
    errors.schema = "Use a SQL, PDF, or JSON schema file.";
  if (files.sampleData && !/\.csv$/i.test(files.sampleData.name))
    errors.sampleData = "Use a CSV file for sample data.";
  return errors;
}
function StatusMessage({ message, success = false }) {
  return message ? (
    <p
      className={`semantic-form-message${success ? " is-success" : ""}`}
      role="status"
    >
      {message}
    </p>
  ) : null;
}

function SourceFileCard({ source, file, error, onChange, onRemove }) {
  const { key, label, type, accept, required, Icon } = source;
  return (
    <article
      className={`source-file-card${file ? "" : " is-missing"}${error ? " is-invalid" : ""}`}
    >
      <div className="source-file-top">
        <div>
          <span className="source-type-icon">
            <Icon aria-hidden="true" />
          </span>
          <strong>
            {label}
            {required ? " *" : ""}
          </strong>
          <small>{type}</small>
        </div>
        {file ? (
          <button
            type="button"
            aria-label={`Remove ${label}`}
            onClick={() => onRemove(key)}
          >
            <IconX aria-hidden="true" />
          </button>
        ) : null}
      </div>
      <label className="source-file-picker">
        <input
          type="file"
          accept={accept || undefined}
          onChange={(event) => onChange(key, event.target.files?.[0] || null)}
        />
        {file ? (
          <div className="source-file-ready">
            <IconFileText aria-hidden="true" />
            <div>
              <b>{file.name}</b>
              <small>
                {Math.max(1, Math.ceil(file.size / 1024))} KB · Ready to upload
              </small>
            </div>
            <span>
              <IconCheck aria-hidden="true" />
            </span>
          </div>
        ) : (
          <div className="source-file-ready">
            <IconFileText aria-hidden="true" />
            <div>
              <b>Add a file</b>
              <small className="source-file-empty">
                Choose from your computer
              </small>
            </div>
          </div>
        )}
      </label>
      {error ? <p className="source-field-error">{error}</p> : null}
    </article>
  );
}

function UploadSources({ onCancel, onUploaded }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [files, setFiles] = useState(EMPTY_FILES);
  const [errors, setErrors] = useState({});
  const [state, setState] = useState("idle");
  const [message, setMessage] = useState("");
  const setFile = (key, file) => {
    setFiles((current) => ({ ...current, [key]: file }));
    setErrors((current) => ({ ...current, [key]: "" }));
  };
  async function submit(event) {
    event.preventDefault();
    const nextErrors = validateUpload({ name, description, files });
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;
    setState("loading");
    setMessage("");
    try {
      const response = await uploadSemanticSources({
        name,
        description,
        files,
      });
      onUploaded(response);
      setState("success");
      setMessage(
        response?.message || "Your data source is ready for draft generation.",
      );
    } catch (error) {
      setState("error");
      setMessage(error.message);
    }
  }
  return (
    <form className="source-upload" onSubmit={submit} noValidate>
      <div className="source-details">
        <h3>Data source details</h3>
        <div className="source-divider" />
        <div className="source-fields">
          <label>
            Source name <b>*</b>
            <input
              aria-label="Source name"
              value={name}
              maxLength="100"
              onChange={(event) => setName(event.target.value)}
              aria-invalid={Boolean(errors.name)}
            />
            {errors.name ? (
              <p className="source-field-error">{errors.name}</p>
            ) : null}
          </label>
          <label>
            Description <b>*</b>
            <input
              aria-label="Description"
              value={description}
              maxLength="500"
              onChange={(event) => setDescription(event.target.value)}
              aria-invalid={Boolean(errors.description)}
            />
            {errors.description ? (
              <p className="source-field-error">{errors.description}</p>
            ) : null}
          </label>
        </div>
      </div>
      <div className="source-files-heading">
        <h3>Source files</h3>
        <span>{sourceCount(files)} / 4 selected</span>
      </div>
      <div className="source-grid">
        {SOURCE_FIELDS.map((source) => (
          <SourceFileCard
            key={source.key}
            source={source}
            file={files[source.key]}
            error={errors[source.key]}
            onChange={setFile}
            onRemove={(key) => setFile(key, null)}
          />
        ))}
      </div>
      <StatusMessage message={message} success={state === "success"} />
      <div className="source-footer">
        <button type="button" onClick={onCancel} disabled={state === "loading"}>
          Cancel
        </button>
        <button
          className="primary"
          type="submit"
          disabled={state === "loading"}
        >
          {state === "loading" ? (
            "Uploading sources…"
          ) : (
            <>
              <IconDatabase aria-hidden="true" /> Save data source
            </>
          )}
        </button>
      </div>
    </form>
  );
}

function Overview({ state, status, onUpload, onGenerate, onRetry }) {
  if (state === "loading")
    return (
      <article className="admin-card semantic-state">
        <IconLoader className="copilot-processing-loader" aria-hidden="true" />
        <h3>Loading your semantic layer</h3>
        <p>Checking the approved data context for Copilot.</p>
      </article>
    );
  if (state === "empty")
    return (
      <article className="admin-card semantic-state">
        <IconLayers aria-hidden="true" />
        <h3>No semantic layer yet</h3>
        <p>
          Add an approved data source to create the business context used by
          Copilot.
        </p>
        <div className="admin-actions">
          <button className="primary" type="button" onClick={onUpload}>
            Add data source
          </button>
        </div>
      </article>
    );
  if (state === "error")
    return (
      <article className="admin-card semantic-state">
        <h3>We couldn’t load the semantic layer</h3>
        <p>Please try again. If this continues, contact your administrator.</p>
        <div className="admin-actions">
          <button type="button" onClick={onRetry}>
            Try again
          </button>
        </div>
      </article>
    );
  const sourceTotal = sourceCount(status?.sources);
  return (
    <div className="admin-content-grid">
      <article className="admin-card semantic-status-card">
        <div className="admin-card-title">
          <div>
            <small>CURRENT LAYER</small>
            <h3>
              {status?.version
                ? `Semantic layer · ${status.version}`
                : "Semantic layer"}
            </h3>
          </div>
          <span className="admin-badge">{status?.status || "Available"}</span>
        </div>
        <p className="semantic-status-meta">
          <strong>Last updated:</strong>{" "}
          {formatTimestamp(status?.buildTimestamp)}
          <br />
          <strong>Latest update:</strong>{" "}
          {status?.lastRegenerationType || "Not available"}
        </p>
        <div className="admin-key-values">
          <span>
            <b>{sourceTotal}</b> Sources
          </span>
          <span>
            <b>{status?.revisionId ? "1" : "0"}</b> Current revision
          </span>
        </div>
        <button type="button" onClick={onUpload}>
          Update sources
        </button>
      </article>
      <article className="admin-card">
        <small>WORKFLOW</small>
        <h3>Generate a new draft</h3>
        <p>
          Use the approved sources to prepare an updated semantic draft for
          review.
        </p>
        <button type="button" onClick={onGenerate}>
          Generate draft
        </button>
      </article>
    </div>
  );
}

function GenerateDraft({ source, status, onBack, onGenerated }) {
  const [generation, setGeneration] = useState("Full");
  const [state, setState] = useState("idle");
  const [message, setMessage] = useState("");
  const [result, setResult] = useState(null);
  const semanticLayerId = source?.semanticLayerId || status?.semanticLayerId;
  const sourceFileIds = source?.sources || status?.sources;
  const canGenerate = Boolean(semanticLayerId && sourceCount(sourceFileIds));
  async function submit() {
    if (!canGenerate) {
      setState("error");
      setMessage("Add a schema source before generating a draft.");
      return;
    }
    setState("loading");
    setMessage("");
    try {
      const response = await generateSemanticDraft({
        semanticLayerId,
        triggerType: generation,
        sourceFileIds,
        baseRevisionId: status?.revisionId || null,
      });
      setResult(response);
      setState("success");
      onGenerated(response);
    } catch (error) {
      setState("error");
      setMessage(error.message);
    }
  }
  return (
    <article className="admin-card admin-form">
      <small>GENERATION</small>
      <h3>Generate semantic draft</h3>
      <p>
        Create a revision from your saved sources. It will remain unavailable to
        Copilot until approved.
      </p>
      <div className="admin-choice">
        <button
          type="button"
          className={generation === "Full" ? "selected" : ""}
          onClick={() => setGeneration("Full")}
        >
          <b>Full rebuild</b>
          <span>Regenerate the complete business context</span>
        </button>
        <button
          type="button"
          className={generation === "Incremental" ? "selected" : ""}
          onClick={() => setGeneration("Incremental")}
        >
          <b>Incremental update</b>
          <span>Build from the current revision</span>
        </button>
      </div>
      <StatusMessage message={message} />
      {result ? (
        <div className="admin-card semantic-draft-result">
          <small>DRAFT READY</small>
          <h3>Draft prepared for review</h3>
          <p>{result.regeneratedObjectsCount || 0} items were refreshed.</p>
          <div className="admin-actions">
            <Link className="primary" to="/admin/review">
              Review draft
            </Link>
          </div>
        </div>
      ) : null}
      <div className="admin-actions">
        <button type="button" onClick={onBack} disabled={state === "loading"}>
          Back
        </button>
        <button
          type="button"
          className="primary"
          disabled={state === "loading"}
          onClick={submit}
        >
          {state === "loading" ? "Generating draft…" : "Generate draft"}
        </button>
      </div>
    </article>
  );
}

export default function AdminSemanticLayer() {
  const [tab, setTab] = useState("overview");
  const [statusState, setStatusState] = useState("loading");
  const [status, setStatus] = useState(null);
  const [uploadedSource, setUploadedSource] = useState(null);
  const loadStatus = async () => {
    setStatusState("loading");
    try {
      setStatus(await getSemanticLayerStatus());
      setStatusState("ready");
    } catch (error) {
      setStatusState(error.status === 404 ? "empty" : "error");
    }
  };
  useEffect(() => {
    Promise.resolve().then(loadStatus);
  }, []);
  const activeStatus = uploadedSource || status;
  return (
    <main className="admin-shell">
      <AdminSidebar active="semantic" />
      <section className="admin-main">
        <AdminTopBar
          title="Semantic Layer"
          description="Maintain the approved business context that powers Copilot answers."
        />
        <div className="admin-tabs">
          <button
            className={tab === "overview" ? "active" : ""}
            type="button"
            onClick={() => setTab("overview")}
          >
            Overview
          </button>
          <button
            className={tab === "upload" ? "active" : ""}
            type="button"
            onClick={() => setTab("upload")}
          >
            Data Sources
          </button>
          <button
            className={tab === "generate" ? "active" : ""}
            type="button"
            onClick={() => setTab("generate")}
          >
            Generate Draft
          </button>
          <Link to="/admin/review">Review drafts</Link>
        </div>
        {tab === "overview" ? (
          <Overview
            state={statusState}
            status={activeStatus}
            onUpload={() => setTab("upload")}
            onGenerate={() => setTab("generate")}
            onRetry={loadStatus}
          />
        ) : null}
        {tab === "upload" ? (
          <UploadSources
            onCancel={() => setTab("overview")}
            onUploaded={(response) => {
              setUploadedSource(response);
              setStatusState("ready");
            }}
          />
        ) : null}
        {tab === "generate" ? (
          <GenerateDraft
            source={uploadedSource}
            status={status}
            onBack={() => setTab("overview")}
            onGenerated={(response) =>
              setStatus((current) => ({ ...current, ...response }))
            }
          />
        ) : null}
      </section>
    </main>
  );
}
