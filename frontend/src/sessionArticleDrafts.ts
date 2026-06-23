export interface EmbeddedImageInput {
  filename: string;
  data_base64: string;
  media_type: string;
}

export type ArticleMode = "manual" | "upload" | "wiki";

export interface ManualArticleDraftState {
  title: string;
  body: string;
  image: EmbeddedImageInput | null;
  imageAltText: string;
  imageCaption: string;
}

export interface UploadArticleDraftState {
  filename: string;
  markdown: string;
  image: EmbeddedImageInput | null;
}

export function buildEmptyManualArticleDraft(): ManualArticleDraftState {
  return {
    title: "",
    body: "",
    image: null,
    imageAltText: "",
    imageCaption: "",
  };
}

export function readBinaryAsBase64(file: File, callback: (payload: EmbeddedImageInput | null) => void): void {
  const reader = new FileReader();
  reader.addEventListener("load", () => {
    const data = reader.result;
    if (typeof data !== "string") {
      callback(null);
      return;
    }
    callback({
      filename: file.name,
      data_base64: data.split(",", 2)[1] || "",
      media_type: file.type || "application/octet-stream",
    });
  });
  reader.addEventListener("error", () => callback(null));
  reader.readAsDataURL(file);
}

export function readTextFile(file: File, callback: (payload: { filename: string; text: string } | null) => void): void {
  const reader = new FileReader();
  reader.addEventListener("load", () => {
    const data = reader.result;
    if (typeof data !== "string") {
      callback(null);
      return;
    }
    callback({ filename: file.name, text: data });
  });
  reader.addEventListener("error", () => callback(null));
  reader.readAsText(file);
}
