import { useState } from "react";
import { useNavigate } from "react-router-dom";
import AdminSidebar from "../components/AdminSidebar";
import AdminTopBar from "../components/AdminTopBar";
import {
  IconBookOpen,
  IconCheck,
  IconDatabase,
  IconFileText,
  IconLayers,
  IconTable,
  IconX,
} from "../components/icons";
import { uploadSemanticSources } from "../services/semanticLayerService";
import "../styles/admin.css";
import "../styles/admin-pages.css";
import "../styles/semantic-layer.css";

const SOURCE_FIELDS = [
  {
    key: "schema",
    label: "Schema definition",
    type: "SQL or JSON",
    accept: ".sql,.json",
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
  else if (!/\.(sql|json)$/i.test(files.schema.name))
    errors.schema = "Use a SQL or JSON schema file.";
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

export default function AdminSemanticLayer() {
  const navigate = useNavigate();
  return (
    <main className="admin-shell">
      <AdminSidebar active="semantic" />
      <section className="admin-main semantic-upload-main">
        <AdminTopBar
          title="Add data source"
          description="Create a new business context for Copilot."
        />
        <UploadSources
          onCancel={() => navigate("/admin/semantic-layers")}
          onUploaded={(response) => {
            const newLayerId = response?.semanticLayerId || response?.SemanticLayerId || response?.data?.semanticLayerId || response?.data?.SemanticLayerId;
            if (newLayerId) {
              navigate(`/admin/semantic-layers/${newLayerId}/sources`, {
                replace: true,
                state: { uploadedSource: response },
              });
            }
          }}
        />
      </section>
    </main>
  );
}
