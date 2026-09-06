export async function api<T>(url:string, options:RequestInit = {}):Promise<T> {
  const response = await fetch('/api' + url, {...options, credentials:'same-origin', headers:{'Content-Type':'application/json','X-BDT-Client':'web', ...options.headers}});
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.status === 204 ? undefined as T : await response.json() as T;
}
export function downloadJSON(name:string, data:unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data,null,2)], {type:'application/json'}));
  const a = document.createElement('a'); a.href=url; a.download=name; a.click();
  setTimeout(()=>URL.revokeObjectURL(url), 1000);
}
