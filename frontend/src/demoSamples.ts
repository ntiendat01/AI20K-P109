const demoDirectory = "/demo";

export const DEMO_ITEMS_FILENAME = "danh_sach_vat_lieu_xay_dung.csv";
export const DEMO_QUOTATION_FILENAMES = ["bao_gia_vlxd_mien_nam.pdf", "bao_gia_vlxd_sai_gon.pdf"] as const;

async function loadDemoFile(filename: string, contentType: string): Promise<File> {
  const response = await fetch(`${demoDirectory}/${filename}`);
  if (!response.ok) throw new Error(`Không tải được file mẫu ${filename}.`);
  return new File([await response.blob()], filename, { type: contentType });
}

export function loadDemoItems(): Promise<File> {
  return loadDemoFile(DEMO_ITEMS_FILENAME, "text/csv");
}

export function loadDemoQuotations(): Promise<File[]> {
  return Promise.all(DEMO_QUOTATION_FILENAMES.map((filename) => loadDemoFile(filename, "application/pdf")));
}
