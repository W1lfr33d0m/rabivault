(function () {
    "use strict";

    const configEl = document.getElementById("vault-config");
    if (!configEl) return;

    const config = JSON.parse(configEl.textContent);
    const csrfToken = document.querySelector('meta[name="csrf-token"]').content;

    const state = {
        currentFolderId: config.initialFolderId ? Number(config.initialFolderId) : null,
        viewMode: localStorage.getItem("vault:viewMode") || "list",
        folders: [],
        documents: [],
        breadcrumbs: [],
        selection: new Set(),
        lastClickedIndex: null,
        searchQuery: "",
        treeChildrenCache: new Map(),
        canUpload: false,
        canCreateFolder: false,
        canDeleteFolder: false,
    };

    const els = {
        tree: document.getElementById("folder-tree"),
        breadcrumbs: document.getElementById("breadcrumbs"),
        contents: document.getElementById("explorer-contents"),
        search: document.getElementById("explorer-search"),
        viewListBtn: document.getElementById("view-list-btn"),
        viewGridBtn: document.getElementById("view-grid-btn"),
        uploadLink: document.getElementById("upload-link"),
        newFolderLink: document.getElementById("new-folder-link"),
        uploadModal: document.getElementById("upload-modal"),
        uploadModalBody: document.getElementById("upload-modal-body"),
        uploadModalClose: document.getElementById("upload-modal-close"),
        toastContainer: document.getElementById("toast-container"),
    };

    // ---------- CSRF fetch helper ----------
    function isAuthGateRedirect(url) {
        return url.indexOf("/account/mfa/verify") !== -1 || url.indexOf("/login/") !== -1;
    }

    async function csrfFetch(url, options) {
        options = options || {};
        const headers = Object.assign({}, options.headers || {});
        if (options.method && options.method !== "GET") {
            headers["X-CSRFToken"] = csrfToken;
        }
        const response = await fetch(url, Object.assign({}, options, { headers }));
        if (response.redirected && isAuthGateRedirect(response.url)) {
            // The API endpoint's own URL is a POST-only JSON route, so sending the
            // user back there after MFA verification would 405. Send them back to
            // this page instead; they can retry the action once verified.
            const redirectUrl = new URL(response.url, window.location.origin);
            redirectUrl.searchParams.set("next", window.location.pathname + window.location.search);
            window.location = redirectUrl.toString();
            return null;
        }
        return response;
    }

    // ---------- Toasts ----------
    function showToast(message, tag) {
        const el = document.createElement("div");
        el.className = "message " + (tag || "info");
        el.textContent = message;
        els.toastContainer.appendChild(el);
        setTimeout(function () {
            el.remove();
        }, 5000);
    }

    function itemKey(type, id) {
        return type + ":" + id;
    }

    function splitKey(key) {
        const idx = key.indexOf(":");
        return [key.slice(0, idx), key.slice(idx + 1)];
    }

    function escapeHtml(value) {
        const div = document.createElement("div");
        div.textContent = value == null ? "" : String(value);
        return div.innerHTML;
    }

    function formatBytes(bytes) {
        if (!bytes) return "0 B";
        const units = ["B", "KB", "MB", "GB"];
        let value = bytes;
        let i = 0;
        while (value >= 1024 && i < units.length - 1) {
            value /= 1024;
            i += 1;
        }
        return value.toFixed(value >= 10 || i === 0 ? 0 : 1) + " " + units[i];
    }

    function iconFor(type, documentType) {
        if (type === "folder") return "📁";
        const icons = {
            pdf: "📕",
            document: "📄",
            spreadsheet: "📊",
            presentation: "📽️",
            image: "🖼️",
            dicom: "🩻",
            archive: "🗜️",
            other: "📄",
        };
        return icons[documentType] || "📄";
    }

    // ---------- Drag helpers ----------
    function isInternalDrag(event) {
        return !!event.dataTransfer && Array.prototype.includes.call(event.dataTransfer.types, "application/x-rabivault-items");
    }

    function isFileDrag(event) {
        return !!event.dataTransfer && Array.prototype.includes.call(event.dataTransfer.types, "Files");
    }

    function resolveFolderId(folderId) {
        return typeof folderId === "function" ? folderId() : folderId;
    }

    function attachDropTarget(el, folderId, options) {
        options = options || {};
        const allowUpload = options.allowUpload !== false;
        const allowInternalMove = options.allowInternalMove !== false;
        let dragCounter = 0;

        el.addEventListener("dragover", function (event) {
            if ((allowInternalMove && isInternalDrag(event)) || (allowUpload && isFileDrag(event))) {
                event.preventDefault();
                event.stopPropagation();
                event.dataTransfer.dropEffect = isFileDrag(event) && !isInternalDrag(event) ? "copy" : "move";
            }
        });

        el.addEventListener("dragenter", function (event) {
            if (allowInternalMove && isInternalDrag(event)) {
                event.stopPropagation();
                dragCounter += 1;
                el.classList.add("drag-over-move");
            } else if (allowUpload && isFileDrag(event)) {
                event.stopPropagation();
                dragCounter += 1;
                el.classList.add("drag-over-upload");
            }
        });

        el.addEventListener("dragleave", function (event) {
            if ((allowInternalMove && isInternalDrag(event)) || (allowUpload && isFileDrag(event))) {
                event.stopPropagation();
                dragCounter -= 1;
                if (dragCounter <= 0) {
                    dragCounter = 0;
                    el.classList.remove("drag-over-move", "drag-over-upload");
                }
            }
        });

        el.addEventListener("drop", async function (event) {
            const internal = allowInternalMove && isInternalDrag(event);
            const file = allowUpload && isFileDrag(event);
            if (!internal && !file) return;

            event.preventDefault();
            event.stopPropagation();
            dragCounter = 0;
            el.classList.remove("drag-over-move", "drag-over-upload");

            const resolvedFolderId = resolveFolderId(folderId);

            if (internal) {
                await handleInternalDrop(event, resolvedFolderId);
            } else {
                handleFileDrop(event, resolvedFolderId);
            }
        });
    }

    // ---------- Folder tree ----------
    async function fetchTreeChildren(parentId) {
        const cacheKey = parentId === null ? "root" : String(parentId);
        if (state.treeChildrenCache.has(cacheKey)) {
            return state.treeChildrenCache.get(cacheKey);
        }
        const params = new URLSearchParams();
        if (parentId !== null) params.set("parent", parentId);
        const response = await csrfFetch(config.urls.tree + "?" + params.toString());
        if (!response || !response.ok) return [];
        const data = await response.json();
        state.treeChildrenCache.set(cacheKey, data.folders);
        return data.folders;
    }

    function invalidateTreeCache(parentId) {
        state.treeChildrenCache.delete(parentId === null ? "root" : String(parentId));
    }

    async function renderTree() {
        els.tree.innerHTML = "";
        els.tree.appendChild(buildTreeRow(null, "Home", false));

        const rootContainer = document.createElement("div");
        rootContainer.className = "tree-children";
        const rootChildren = await fetchTreeChildren(null);
        rootChildren.forEach(function (folder) {
            rootContainer.appendChild(buildTreeNode(folder));
        });
        els.tree.appendChild(rootContainer);
        highlightActiveTreeRow();
    }

    function buildTreeNode(folder) {
        const wrapper = document.createElement("div");
        wrapper.className = "tree-node";
        wrapper.dataset.folderId = folder.id;
        wrapper.appendChild(buildTreeRow(folder.id, folder.name, folder.has_children));

        const childrenContainer = document.createElement("div");
        childrenContainer.className = "tree-children";
        childrenContainer.hidden = true;
        wrapper.appendChild(childrenContainer);
        return wrapper;
    }

    function buildTreeRow(folderId, name, hasChildren) {
        const row = document.createElement("div");
        row.className = "tree-node-row";
        row.dataset.folderId = folderId === null ? "" : folderId;
        row.setAttribute("tabindex", "0");
        row.setAttribute("draggable", "true");

        const caret = document.createElement("button");
        caret.type = "button";
        caret.className = "tree-caret" + (hasChildren ? "" : " leaf");
        caret.innerHTML = "&#9656;";
        caret.setAttribute("aria-expanded", "false");
        if (!hasChildren) caret.disabled = true;
        row.appendChild(caret);

        const label = document.createElement("span");
        label.textContent = name;
        row.appendChild(label);

        caret.addEventListener("click", async function (event) {
            event.stopPropagation();
            if (!hasChildren) return;

            const wrapper = row.parentElement;
            const childrenContainer = wrapper.querySelector(":scope > .tree-children");
            const expanded = caret.classList.toggle("expanded");
            caret.setAttribute("aria-expanded", expanded ? "true" : "false");

            if (expanded) {
                if (!childrenContainer.dataset.loaded) {
                    const children = await fetchTreeChildren(folderId);
                    children.forEach(function (child) {
                        childrenContainer.appendChild(buildTreeNode(child));
                    });
                    childrenContainer.dataset.loaded = "true";
                }
                childrenContainer.hidden = false;
            } else {
                childrenContainer.hidden = true;
            }
        });

        row.addEventListener("click", function () {
            navigateTo(folderId === null ? null : Number(folderId));
        });

        row.addEventListener("dragstart", function (event) {
            event.preventDefault();
        });

        attachDropTarget(row, folderId === null ? null : Number(folderId));

        return row;
    }

    function highlightActiveTreeRow() {
        els.tree.querySelectorAll(".tree-node-row").forEach(function (row) {
            const id = row.dataset.folderId === "" ? null : Number(row.dataset.folderId);
            row.classList.toggle("active", id === state.currentFolderId);
        });
    }

    // ---------- Breadcrumbs ----------
    function renderBreadcrumbs() {
        els.breadcrumbs.innerHTML = "";
        state.breadcrumbs.forEach(function (crumb, index) {
            if (index > 0) {
                const sep = document.createElement("span");
                sep.className = "breadcrumb-sep";
                sep.textContent = "/";
                els.breadcrumbs.appendChild(sep);
            }

            const isCurrent = index === state.breadcrumbs.length - 1;
            const el = document.createElement(isCurrent ? "span" : "a");
            el.className = "breadcrumb-item" + (isCurrent ? " current" : "");
            el.textContent = crumb.name;

            if (!isCurrent) {
                el.href = "#";
                el.addEventListener("click", function (event) {
                    event.preventDefault();
                    navigateTo(crumb.id);
                });
                attachDropTarget(el, crumb.id, { allowUpload: false });
            }

            els.breadcrumbs.appendChild(el);
        });
    }

    // ---------- Navigation & contents ----------
    function navigateTo(folderId) {
        state.searchQuery = "";
        els.search.value = "";
        state.currentFolderId = folderId;
        loadContents();
    }

    async function loadContents() {
        els.contents.innerHTML = '<p class="empty-state">Loading&hellip;</p>';

        const params = new URLSearchParams();
        if (state.searchQuery) {
            params.set("q", state.searchQuery);
        } else if (state.currentFolderId !== null) {
            params.set("folder", state.currentFolderId);
        }

        const response = await csrfFetch(config.urls.contents + "?" + params.toString());
        if (!response) return;

        if (!response.ok) {
            els.contents.innerHTML = '<p class="empty-state">Could not load this folder.</p>';
            return;
        }

        const data = await response.json();
        state.folders = data.folders;
        state.documents = data.documents;
        state.breadcrumbs = state.searchQuery ? [{ id: null, name: "Search results" }] : data.breadcrumbs;
        state.canUpload = data.can_upload;
        state.canCreateFolder = data.can_create_folder;
        state.canDeleteFolder = data.can_delete_folder;
        state.selection.clear();
        state.lastClickedIndex = null;

        renderBreadcrumbs();
        renderContents();
        updateToolbarLinks();
        highlightActiveTreeRow();
    }

    function updateToolbarLinks() {
        const folderParam = state.currentFolderId !== null ? "?folder=" + state.currentFolderId : "";
        els.uploadLink.href = config.urls.documentUpload + folderParam;
        const parentParam = state.currentFolderId !== null ? "?parent=" + state.currentFolderId : "";
        els.newFolderLink.href = config.urls.folderCreate + parentParam;
    }

    function renderContents() {
        els.contents.classList.toggle("list-view", state.viewMode === "list");
        els.contents.classList.toggle("grid-view", state.viewMode === "grid");

        if (!state.folders.length && !state.documents.length) {
            els.contents.innerHTML = '<p class="empty-state">This folder is empty. Upload a file or create a subfolder to get started.</p>';
            return;
        }

        if (state.viewMode === "grid") {
            renderGrid();
        } else {
            renderList();
        }

        attachItemBehaviors();
    }

    function renderGrid() {
        const grid = document.createElement("div");
        grid.className = "contents-grid";

        state.folders.forEach(function (folder) {
            const tile = document.createElement("div");
            tile.className = "tile item";
            tile.dataset.type = "folder";
            tile.dataset.id = folder.id;
            tile.dataset.name = folder.name;
            tile.setAttribute("draggable", "true");
            tile.setAttribute("tabindex", "0");
            tile.innerHTML =
                '<div class="tile-icon">' + iconFor("folder") + "</div>" +
                '<div class="tile-name">' + escapeHtml(folder.name) + "</div>" +
                '<div class="tile-meta">' + folder.subfolder_count + " folders · " + folder.document_count + " files</div>";
            grid.appendChild(tile);
        });

        state.documents.forEach(function (doc) {
            const tile = document.createElement("div");
            tile.className = "tile item";
            tile.dataset.type = "document";
            tile.dataset.id = doc.public_id;
            tile.dataset.name = doc.title;
            tile.setAttribute("draggable", "true");
            tile.setAttribute("tabindex", "0");
            tile.innerHTML =
                '<div class="tile-icon">' + iconFor("document", doc.document_type) + "</div>" +
                '<div class="tile-name">' + escapeHtml(doc.title) + "</div>" +
                '<div class="tile-meta">' + formatBytes(doc.file_size) + "</div>";
            grid.appendChild(tile);
        });

        els.contents.innerHTML = "";
        els.contents.appendChild(grid);
    }

    function renderList() {
        const wrap = document.createElement("div");
        wrap.className = "table-wrap";
        const table = document.createElement("table");
        table.innerHTML = "<thead><tr><th>Name</th><th>Type</th><th>Facility</th><th>Status</th><th>Size</th><th>Uploaded</th></tr></thead>";
        const tbody = document.createElement("tbody");

        state.folders.forEach(function (folder) {
            const tr = document.createElement("tr");
            tr.className = "item";
            tr.dataset.type = "folder";
            tr.dataset.id = folder.id;
            tr.dataset.name = folder.name;
            tr.setAttribute("draggable", "true");
            tr.setAttribute("tabindex", "0");
            tr.innerHTML =
                '<td><div class="item-name-cell"><span class="item-icon">' + iconFor("folder") + '</span><span class="item-label">' + escapeHtml(folder.name) + "</span></div></td>" +
                "<td>Folder</td>" +
                "<td>" + escapeHtml(folder.facility_name || "Organization-level") + "</td>" +
                "<td>" + folder.subfolder_count + " folders, " + folder.document_count + " files</td>" +
                "<td>—</td><td>—</td>";
            tbody.appendChild(tr);
        });

        state.documents.forEach(function (doc) {
            const tr = document.createElement("tr");
            tr.className = "item";
            tr.dataset.type = "document";
            tr.dataset.id = doc.public_id;
            tr.dataset.name = doc.title;
            tr.setAttribute("draggable", "true");
            tr.setAttribute("tabindex", "0");
            const scanBadge = '<span class="badge ' + doc.scan_status + '">' + escapeHtml(doc.scan_status_display) + "</span>";
            tr.innerHTML =
                '<td><div class="item-name-cell"><span class="item-icon">' + iconFor("document", doc.document_type) + '</span><span class="item-label">' + escapeHtml(doc.title) + "</span></div></td>" +
                "<td>" + escapeHtml(doc.document_type_display) + "</td>" +
                "<td>" + escapeHtml(doc.facility_name || "Organization-level") + "</td>" +
                "<td>" + scanBadge + "</td>" +
                "<td>" + formatBytes(doc.file_size) + "</td>" +
                "<td>" + new Date(doc.created_at).toLocaleString() + "</td>";
            tbody.appendChild(tr);
        });

        table.appendChild(tbody);
        wrap.appendChild(table);
        els.contents.innerHTML = "";
        els.contents.appendChild(wrap);
    }

    // ---------- Selection & item behaviors ----------
    function attachItemBehaviors() {
        const items = Array.from(els.contents.querySelectorAll(".item"));

        items.forEach(function (el, index) {
            updateSelectedClass(el);

            el.addEventListener("click", function (event) {
                handleItemClick(event, el, items, index);
            });

            el.addEventListener("dblclick", function () {
                openItem(el);
            });

            el.addEventListener("keydown", function (event) {
                if (event.key === "Enter") openItem(el);
            });

            el.addEventListener("contextmenu", function (event) {
                event.preventDefault();
                event.stopPropagation();
                if (!state.selection.has(itemKey(el.dataset.type, el.dataset.id))) {
                    selectOnly(el, index);
                    renderSelectionClasses(items);
                }
                openContextMenu(event.clientX, event.clientY, el);
            });

            el.addEventListener("dragstart", function (event) {
                onItemDragStart(event, el, items, index);
            });

            if (el.dataset.type === "folder") {
                attachDropTarget(el, Number(el.dataset.id));
            }
        });
    }

    function updateSelectedClass(el) {
        el.classList.toggle("selected", state.selection.has(itemKey(el.dataset.type, el.dataset.id)));
    }

    function renderSelectionClasses(items) {
        items.forEach(updateSelectedClass);
    }

    function selectOnly(el, index) {
        state.selection.clear();
        state.selection.add(itemKey(el.dataset.type, el.dataset.id));
        state.lastClickedIndex = index;
    }

    function handleItemClick(event, el, items, index) {
        const key = itemKey(el.dataset.type, el.dataset.id);

        if (event.shiftKey && state.lastClickedIndex != null) {
            const start = Math.min(state.lastClickedIndex, index);
            const end = Math.max(state.lastClickedIndex, index);
            state.selection.clear();
            for (let i = start; i <= end; i += 1) {
                state.selection.add(itemKey(items[i].dataset.type, items[i].dataset.id));
            }
        } else if (event.ctrlKey || event.metaKey) {
            if (state.selection.has(key)) {
                state.selection.delete(key);
            } else {
                state.selection.add(key);
            }
            state.lastClickedIndex = index;
        } else {
            state.selection.clear();
            state.selection.add(key);
            state.lastClickedIndex = index;
        }

        renderSelectionClasses(items);
    }

    function openItem(el) {
        if (el.dataset.type === "folder") {
            navigateTo(Number(el.dataset.id));
        } else {
            const doc = state.documents.find(function (d) { return d.public_id === el.dataset.id; });
            if (doc) window.location = doc.detail_url;
        }
    }

    // ---------- Drag and drop (move) ----------
    function onItemDragStart(event, el, items, index) {
        const key = itemKey(el.dataset.type, el.dataset.id);
        if (!state.selection.has(key)) {
            selectOnly(el, index);
            renderSelectionClasses(items);
        }
        const payload = Array.from(state.selection).map(function (selKey) {
            const parts = splitKey(selKey);
            return { type: parts[0], id: parts[1] };
        });
        event.dataTransfer.setData("application/x-rabivault-items", JSON.stringify(payload));
        event.dataTransfer.effectAllowed = "move";
    }

    async function handleInternalDrop(event, targetFolderId) {
        const raw = event.dataTransfer.getData("application/x-rabivault-items");
        if (!raw) return;

        let items;
        try {
            items = JSON.parse(raw);
        } catch (err) {
            return;
        }

        let succeeded = 0;
        let failed = 0;
        let lastError = "";

        for (const item of items) {
            if (item.type === "folder" && Number(item.id) === targetFolderId) continue;

            const url = item.type === "folder" ? config.urls.folderMove : config.urls.documentMove;
            const body = item.type === "folder"
                ? { folder_id: Number(item.id), new_parent_id: targetFolderId }
                : { public_id: item.id, folder_id: targetFolderId };

            const response = await csrfFetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            if (!response) return;

            if (response.ok) {
                succeeded += 1;
            } else {
                failed += 1;
                const data = await response.json().catch(function () { return {}; });
                lastError = data.error || "Move failed.";
            }
        }

        if (succeeded) {
            invalidateTreeCache(targetFolderId);
            invalidateTreeCache(state.currentFolderId);
            showToast(succeeded + " item(s) moved.", "active");
        }
        if (failed) {
            showToast(failed + " item(s) could not be moved: " + lastError, "infected");
        }

        renderTree();
        loadContents();
    }

    function handleFileDrop(event, targetFolderId) {
        const files = event.dataTransfer.files;
        if (!files || !files.length) return;

        if (files.length > 1) {
            showToast(
                "RabiVault captures metadata per file, so files upload one at a time. Opening the form for \"" + files[0].name + "\".",
                "pending"
            );
        }

        openUploadModal(targetFolderId, files[0]);
    }

    // ---------- Upload modal ----------
    async function openUploadModal(folderId, file) {
        const params = folderId !== null ? "?folder=" + folderId : "";
        const response = await csrfFetch(config.urls.documentUpload + params, {
            headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        if (!response) return;

        if (response.redirected) {
            showToast("Upload isn't available right now. Check your organization and BAA status.", "infected");
            return;
        }

        if (!response.ok) {
            showToast("Could not open the upload form.", "infected");
            return;
        }

        const html = await response.text();
        els.uploadModalBody.innerHTML = html;

        if (file) {
            const fileInput = els.uploadModalBody.querySelector('input[type="file"]');
            if (fileInput) {
                const dt = new DataTransfer();
                dt.items.add(file);
                fileInput.files = dt.files;
            }
            const titleInput = els.uploadModalBody.querySelector("#id_title");
            if (titleInput && !titleInput.value) {
                titleInput.value = file.name.replace(/\.[^/.]+$/, "");
            }
        }

        els.uploadModalBody.querySelectorAll(".cancel-upload").forEach(function (link) {
            link.addEventListener("click", function (event) {
                event.preventDefault();
                els.uploadModal.close();
            });
        });

        els.uploadModal.showModal();
    }

    els.uploadModalClose.addEventListener("click", function () {
        els.uploadModal.close();
    });

    els.uploadLink.addEventListener("click", function (event) {
        event.preventDefault();
        openUploadModal(state.currentFolderId, null);
    });

    // ---------- Context menu ----------
    let openMenu = null;

    function closeContextMenu() {
        if (openMenu) {
            openMenu.remove();
            openMenu = null;
        }
        document.removeEventListener("click", handleOutsideClick);
        document.removeEventListener("scroll", handleScrollClose, true);
    }

    function openContextMenu(x, y, el) {
        closeContextMenu();

        const multi = state.selection.size > 1;
        const type = el.dataset.type;
        const menu = document.createElement("ul");
        menu.className = "context-menu";

        function addItem(label, handler, opts) {
            opts = opts || {};
            const li = document.createElement("li");
            const button = document.createElement("button");
            button.type = "button";
            button.textContent = label;
            if (opts.danger) button.classList.add("danger");
            if (opts.disabled) button.disabled = true;
            button.addEventListener("click", function () {
                closeContextMenu();
                handler();
            });
            li.appendChild(button);
            menu.appendChild(li);
        }

        if (!multi && type === "document") {
            const doc = state.documents.find(function (d) { return d.public_id === el.dataset.id; });
            addItem("Open", function () { window.location = doc.detail_url; });
            addItem("Download", function () { window.location = doc.download_url; });
            addItem("Rename", function () { startRename(el); });
            menu.appendChild(document.createElement("hr"));
            addItem("Delete", function () { window.location = doc.delete_url; }, { danger: true });
        } else if (!multi && type === "folder") {
            const folder = state.folders.find(function (f) { return String(f.id) === el.dataset.id; });
            const canDelete = !!folder && folder.subfolder_count === 0 && folder.document_count === 0;
            addItem("Open", function () { navigateTo(Number(el.dataset.id)); });
            addItem("Rename", function () { startRename(el); });
            menu.appendChild(document.createElement("hr"));
            addItem("Delete", function () { deleteFolder(Number(el.dataset.id)); }, {
                danger: true,
                disabled: !canDelete,
            });
        } else if (multi) {
            addItem("Delete selected", function () { deleteSelection(); }, { danger: true });
        } else {
            addItem("Upload file", function () { openUploadModal(state.currentFolderId, null); }, {
                disabled: !state.canUpload,
            });
            addItem("New folder", function () { window.location = els.newFolderLink.href; }, {
                disabled: !state.canCreateFolder,
            });
        }

        document.body.appendChild(menu);
        const rect = menu.getBoundingClientRect();
        const left = Math.max(8, Math.min(x, window.innerWidth - rect.width - 8));
        const top = Math.max(8, Math.min(y, window.innerHeight - rect.height - 8));
        menu.style.left = left + "px";
        menu.style.top = top + "px";

        openMenu = menu;

        // Opening the menu itself can trigger a same-turn click bubble and/or a
        // browser scroll-into-view (e.g. positioning near the viewport edge).
        // Deferring these listeners by a tick keeps that from immediately closing
        // the menu it just opened.
        setTimeout(function () {
            document.addEventListener("click", handleOutsideClick);
            document.addEventListener("scroll", handleScrollClose, true);
        }, 0);
    }

    function handleOutsideClick(event) {
        if (openMenu && !openMenu.contains(event.target)) closeContextMenu();
    }

    function handleScrollClose() {
        closeContextMenu();
    }

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") closeContextMenu();
    });

    els.contents.addEventListener("contextmenu", function (event) {
        event.preventDefault();
        state.selection.clear();
        renderSelectionClasses(Array.from(els.contents.querySelectorAll(".item")));
        openContextMenu(event.clientX, event.clientY, { dataset: { type: "background" } });
    });

    // ---------- Rename ----------
    function startRename(el) {
        const nameCell = el.querySelector(".item-label") || el.querySelector(".tile-name") || el;
        const currentName = el.dataset.name;
        const input = document.createElement("input");
        input.type = "text";
        input.className = "rename-input";
        input.value = currentName;
        nameCell.replaceWith(input);
        input.focus();
        input.select();

        let settled = false;

        async function commit() {
            if (settled) return;
            settled = true;
            const newName = input.value.trim();
            if (!newName || newName === currentName) {
                loadContents();
                return;
            }

            const isFolder = el.dataset.type === "folder";
            const url = isFolder ? config.urls.folderRename : config.urls.documentRename;
            const body = isFolder
                ? { folder_id: Number(el.dataset.id), name: newName }
                : { public_id: el.dataset.id, title: newName };

            const response = await csrfFetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            if (!response) return;

            if (response.ok) {
                showToast("Renamed successfully.", "active");
                invalidateTreeCache(state.currentFolderId);
                renderTree();
            } else {
                const data = await response.json().catch(function () { return {}; });
                showToast(data.error || "Rename failed.", "infected");
            }
            loadContents();
        }

        input.addEventListener("blur", commit);
        input.addEventListener("keydown", function (event) {
            // Without this, Enter/Escape bubble to the row's own keydown handler
            // (which opens the item on Enter), navigating away mid-rename.
            event.stopPropagation();
            if (event.key === "Enter") input.blur();
            if (event.key === "Escape") {
                settled = true;
                loadContents();
            }
        });
    }

    // ---------- Delete ----------
    async function deleteFolder(folderId) {
        if (!window.confirm("Delete this folder? This cannot be undone.")) return;

        const response = await csrfFetch(config.urls.folderDelete, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ folder_id: folderId }),
        });
        if (!response) return;

        if (response.ok) {
            showToast("Folder deleted.", "active");
            invalidateTreeCache(state.currentFolderId);
            renderTree();
            loadContents();
        } else {
            const data = await response.json().catch(function () { return {}; });
            showToast(data.error || "Could not delete folder.", "infected");
        }
    }

    async function deleteSelection() {
        const keys = Array.from(state.selection);
        const folderKeys = keys.filter(function (key) { return key.indexOf("folder:") === 0; });
        const documentKeys = keys.filter(function (key) { return key.indexOf("document:") === 0; });

        if (documentKeys.length && !window.confirm("Delete " + documentKeys.length + " document(s)? This cannot be undone.")) {
            return;
        }
        if (folderKeys.length && !window.confirm("Delete " + folderKeys.length + " empty folder(s)? This cannot be undone.")) {
            return;
        }

        for (const key of documentKeys) {
            const id = splitKey(key)[1];
            const doc = state.documents.find(function (d) { return d.public_id === id; });
            if (!doc) continue;
            const response = await csrfFetch(doc.delete_url, {
                method: "POST",
                headers: { "X-Requested-With": "XMLHttpRequest" },
            });
            if (!response) return;
        }

        for (const key of folderKeys) {
            const id = splitKey(key)[1];
            const response = await csrfFetch(config.urls.folderDelete, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ folder_id: Number(id) }),
            });
            if (!response) return;
        }

        showToast("Delete requests processed.", "active");
        invalidateTreeCache(state.currentFolderId);
        renderTree();
        loadContents();
    }

    // ---------- View toggle ----------
    function setViewMode(mode) {
        state.viewMode = mode;
        localStorage.setItem("vault:viewMode", mode);
        els.viewListBtn.classList.toggle("active", mode === "list");
        els.viewGridBtn.classList.toggle("active", mode === "grid");
        renderContents();
    }

    els.viewListBtn.addEventListener("click", function () { setViewMode("list"); });
    els.viewGridBtn.addEventListener("click", function () { setViewMode("grid"); });

    // ---------- Search ----------
    let searchDebounce = null;
    els.search.addEventListener("input", function () {
        clearTimeout(searchDebounce);
        searchDebounce = setTimeout(function () {
            state.searchQuery = els.search.value.trim();
            loadContents();
        }, 300);
    });

    // ---------- OS file drop safety net & main pane drop target ----------
    attachDropTarget(els.contents, function () { return state.currentFolderId; }, {
        allowUpload: true,
        allowInternalMove: false,
    });

    document.addEventListener("dragover", function (event) {
        if (isFileDrag(event)) event.preventDefault();
    });
    document.addEventListener("drop", function (event) {
        if (isFileDrag(event)) event.preventDefault();
    });

    // ---------- Init ----------
    setViewMode(state.viewMode);
    renderTree();
    loadContents();
})();
