import React from 'react';
import { User, Upload, PanelRightOpen, PanelRightClose } from 'lucide-react';

interface HeaderProps {
  isSidebarOpen: boolean;
  onToggleSidebar: () => void;
  onUploadStatement: (file: File) => void;
  isUploading?: boolean;
}

export function Header({
  isSidebarOpen,
  onToggleSidebar,
  onUploadStatement,
  isUploading,
}: HeaderProps) {
  const handleUpload = () => {
    // File upload handler
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.pdf,.csv,.xlsx';
    input.onchange = (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (file) {
        onUploadStatement(file);
      }
    };
    input.click();
  };

  return (
    <header className="border-b border-[#dfe5e3] bg-white">
      <div className="flex items-center justify-between px-8 py-4">
        <div>
          <div className="text-lg font-semibold text-[#172026]">FinDesk</div>
          <div className="mt-0.5 text-xs text-[#697571]">
            Personal finance operations and agent review
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleUpload}
            className="flex items-center gap-2 rounded-xl border border-[#ccd6d3] bg-white px-4 py-2 text-sm text-[#24302c] transition-colors hover:bg-[#f7f8f8] disabled:opacity-60"
            disabled={isUploading}
          >
            <Upload className="h-4 w-4" />
            {isUploading ? "Uploading" : "Upload Statement"}
          </button>

          <div className="hidden items-center gap-3 border-l border-[#dfe5e3] pl-4 md:flex">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#eef2f1]">
              <User className="h-4 w-4 text-[#53615d]" />
            </div>
            <span className="text-sm text-[#53615d]">Demo profile</span>
          </div>

          <button
            onClick={onToggleSidebar}
            className="flex items-center gap-2 rounded-xl bg-[#172026] px-3 py-2 text-sm text-white transition-colors hover:bg-[#24302c]"
            title={isSidebarOpen ? "Close Agent Team" : "Open Agent Team"}
          >
            {isSidebarOpen ? (
              <PanelRightClose className="h-4 w-4" />
            ) : (
              <PanelRightOpen className="h-4 w-4" />
            )}
            <span>Agent Team</span>
          </button>
        </div>
      </div>
    </header>
  );
}
