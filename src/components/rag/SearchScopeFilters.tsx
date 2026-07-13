"use client";

import type { VaultFolder } from "@/lib/api/vault";

export interface SearchScopeValue {
  folderIds: string[];
  createdAfter: string;
  createdBefore: string;
  indexedOnly: boolean;
}

export const defaultSearchScope: SearchScopeValue = {
  folderIds: [],
  createdAfter: "",
  createdBefore: "",
  indexedOnly: true,
};

export function SearchScopeFilters({
  folders,
  value,
  onChange,
  loadingFolders,
}: {
  folders: VaultFolder[];
  value: SearchScopeValue;
  onChange: (next: SearchScopeValue) => void;
  loadingFolders?: boolean;
}) {
  function toggleFolder(id: string) {
    const next = value.folderIds.includes(id)
      ? value.folderIds.filter((f) => f !== id)
      : [...value.folderIds, id];
    onChange({ ...value, folderIds: next });
  }

  return (
    <div className="rag-panel">
      <h3 className="rag-scope-title">Vault scope</h3>
      <fieldset className="rag-scope-fieldset">
        <legend>Folders</legend>
        {loadingFolders ? (
          <p className="rag-muted">Loading folders…</p>
        ) : folders.length === 0 ? (
          <p className="rag-muted">No vault folders</p>
        ) : (
          <ul className="rag-scope-folder-list">
            {folders.map((folder) => (
              <li key={folder.id}>
                <label className="rag-scope-folder-label">
                  <input
                    type="checkbox"
                    checked={value.folderIds.includes(folder.id)}
                    onChange={() => toggleFolder(folder.id)}
                  />
                  <span>
                    {folder.name}{" "}
                    <span className="rag-muted">({folder.file_count} files)</span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
      </fieldset>

      <div className="rag-scope-dates">
        <label htmlFor="created-after">
          Created after
          <input
            id="created-after"
            type="date"
            className="rag-input"
            value={value.createdAfter}
            onChange={(e) => onChange({ ...value, createdAfter: e.target.value })}
          />
        </label>
        <label htmlFor="created-before">
          Created before
          <input
            id="created-before"
            type="date"
            className="rag-input"
            value={value.createdBefore}
            onChange={(e) => onChange({ ...value, createdBefore: e.target.value })}
          />
        </label>
      </div>

      <p className="rag-muted rag-scope-indexed-note">
        Search includes indexed files only.
      </p>
    </div>
  );
}
