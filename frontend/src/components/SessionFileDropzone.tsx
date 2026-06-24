import { useState, type ChangeEvent, type DragEvent } from "react";

interface SessionFileDropzoneProps {
  id: string;
  label: string;
  accept?: string;
  disabled?: boolean;
  selectedFileName?: string;
  onFileSelected: (file: File | null) => void;
}

export function SessionFileDropzone({
  id,
  label,
  accept,
  disabled = false,
  selectedFileName,
  onFileSelected,
}: SessionFileDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const labelId = `${id}-label`;
  const descriptionId = `${id}-description`;
  const fileNameId = `${id}-selected-file`;

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    onFileSelected(event.currentTarget.files?.item(0) ?? null);
  };

  const handleDragOver = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    if (disabled) {
      event.dataTransfer.dropEffect = "none";
      setIsDragging(false);
      return;
    }
    event.dataTransfer.dropEffect = "copy";
    setIsDragging(true);
  };

  const handleDragLeave = (event: DragEvent<HTMLLabelElement>) => {
    const nextTarget = event.relatedTarget;
    if (!(nextTarget instanceof Node) || !event.currentTarget.contains(nextTarget)) {
      setIsDragging(false);
    }
  };

  const handleDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setIsDragging(false);
    if (disabled) {
      return;
    }
    const file = event.dataTransfer.files?.item(0) ?? null;
    if (file) {
      onFileSelected(file);
    }
  };

  return (
    <div className="field session-file-field">
      <label className="session-file-field__label" htmlFor={id} id={labelId}>
        {label}
      </label>
      <input
        className="session-file-input"
        id={id}
        type="file"
        accept={accept}
        disabled={disabled}
        aria-labelledby={labelId}
        aria-describedby={`${descriptionId} ${fileNameId}`}
        onChange={handleFileChange}
      />
      <label
        className={`session-file-dropzone${isDragging ? " is-dragging" : ""}`}
        htmlFor={id}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <strong>Drag and drop a file here</strong>
        <span className="meta" id={descriptionId}>or use Browse to choose one</span>
        <span className="session-file-dropzone__browse">Browse</span>
        <span className="meta session-file-dropzone__name" id={fileNameId} aria-live="polite">
          {selectedFileName || "No file selected."}
        </span>
      </label>
    </div>
  );
}
