import { useEffect, useRef, useState } from "react";
import { IconChevronDown, IconDownload, IconPrinter } from "./icons";
import { exportToExcel, exportToWord, printResult } from "../utils/exportResult";

export default function ExportMenu({ payload }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onClickOutside = (event) => {
      if (rootRef.current && !rootRef.current.contains(event.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  const run = (action) => {
    action(payload);
    setOpen(false);
  };

  return (
    <div className="export-menu" ref={rootRef}>
      <button
        type="button"
        className="export-menu-trigger"
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <IconDownload aria-hidden="true" /> Download <IconChevronDown aria-hidden="true" />
      </button>
      {open ? (
        <div className="export-menu-list" role="menu">
          <button type="button" role="menuitem" onClick={() => run(exportToExcel)}>
            Excel (.xlsx)
          </button>
          <button type="button" role="menuitem" onClick={() => run(exportToWord)}>
            Word (.doc)
          </button>
          <button type="button" role="menuitem" onClick={() => run(printResult)}>
            <IconPrinter aria-hidden="true" /> Print
          </button>
        </div>
      ) : null}
    </div>
  );
}
