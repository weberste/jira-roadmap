/**
 * Roadmap timeline rendering.
 * Pure HTML/CSS/JS — no extra libraries.
 */

var STATUS_COLORS = {
    'new':           '#8b949e', // gray   (To Do)
    'indeterminate': '#0969da', // blue   (In Progress)
    'done':          '#2da44e', // green  (Done)
    'cancelled':     '#9e3e3e'  // red    (Cancelled)
};


var PIXELS_PER_DAY    = 4;    // overridden at init based on container width
var PROJECT_COL_WIDTH = 90;
var LABEL_WIDTH       = 300;
var STATUS_COL_WIDTH  = 120;
var VIEW_MONTHS       = 13;   // months shown in nav label (1 past + current + 11 future)
var VISIBLE_MONTHS    = 13;   // months that should fill the visible timeline area

// Status categories hidden per row type. Default: hide cancelled only.
var hiddenInitCategories = { 'cancelled': true };
var hiddenEpicCategories = { 'cancelled': true };
// Project keys hidden per row type. Empty = all visible (default).
var hiddenInitProjects = {};
var hiddenEpicProjects = {};
var expanded = {};

// State shared between init and nav helpers
var rmOuter              = null;
var rmTimelineStart      = null;
var rmViewStart          = null;  // first-of-month date at the left edge of the visible window
var rmTotalTimelineWidth = 0;     // total pixel width of the timeline area
var rmNoDateLeft         = 0;     // left px for bars with no start date
var rmRedrawArrows       = null;  // function to redraw dependency arrows; set during init
var rmShowDeps           = false; // dependency arrows hidden by default

function buildFilterDropdownHtml(projects, projectNames) {
    var names = projectNames || {};
    var h = '';
    h += '<div class="rm-filter-section-header">Status</div>';
    h += '<label class="rm-filter-opt"><span class="rm-filter-dot" style="background:#8b949e"></span><input type="checkbox" data-filter="status" value="new" checked> To Do</label>';
    h += '<label class="rm-filter-opt"><span class="rm-filter-dot" style="background:#0969da"></span><input type="checkbox" data-filter="status" value="indeterminate" checked> In Progress</label>';
    h += '<label class="rm-filter-opt"><span class="rm-filter-dot" style="background:#2da44e"></span><input type="checkbox" data-filter="status" value="done" checked> Done</label>';
    h += '<label class="rm-filter-opt"><span class="rm-filter-dot" style="background:#9e3e3e"></span><input type="checkbox" data-filter="status" value="cancelled"> Cancelled</label>';
    if (projects.length > 0) {
        h += '<div class="rm-filter-divider"></div>';
        h += '<div class="rm-filter-section-header">Project</div>';
        for (var i = 0; i < projects.length; i++) {
            var key   = projects[i];
            var label = names[key] || key;
            h += '<label class="rm-filter-opt"><input type="checkbox" data-filter="project" value="' + escAttr(key) + '" checked> ' + escHtml(label) + '</label>';
        }
    }
    return h;
}

function initRoadmap(data) {
    var container = document.getElementById('roadmap-timeline');
    if (!container || !data || !data.initiatives.length) return;
    rmShowDeps = false;

    var today = new Date();
    today.setHours(0, 0, 0, 0);

    // Collect unique project keys (prefix before the first '-' in each key)
    var initProjectsSet = {}, epicProjectsSet = {};
    for (var pi = 0; pi < data.initiatives.length; pi++) {
        var pInit = data.initiatives[pi];
        initProjectsSet[pInit.key.split('-')[0]] = true;
        for (var pe = 0; pe < pInit.epics.length; pe++) {
            epicProjectsSet[pInit.epics[pe].key.split('-')[0]] = true;
        }
    }
    var initProjects = Object.keys(initProjectsSet).sort();
    var epicProjects = Object.keys(epicProjectsSet).sort();

    // Sort initiatives by start date ascending; nulls last
    data.initiatives.sort(function(a, b) {
        if (!a.start_date && !b.start_date) return 0;
        if (!a.start_date) return 1;
        if (!b.start_date) return -1;
        return a.start_date < b.start_date ? -1 : a.start_date > b.start_date ? 1 : 0;
    });

    var timelineStart = new Date(data.timeline_start + 'T00:00:00');
    var timelineEnd   = new Date(data.timeline_end   + 'T00:00:00');
    rmTimelineStart   = timelineStart;

    // Full list of months across the data range (for headers + gridlines)
    var months = [];
    var cursor = new Date(timelineStart.getFullYear(), timelineStart.getMonth(), 1);
    while (cursor <= timelineEnd) {
        months.push(new Date(cursor));
        cursor.setMonth(cursor.getMonth() + 1);
    }

    // Scale PIXELS_PER_DAY so that VISIBLE_MONTHS fill the available timeline width
    var availableWidth = container.clientWidth - PROJECT_COL_WIDTH - LABEL_WIDTH - STATUS_COL_WIDTH;
    if (availableWidth > 0) {
        PIXELS_PER_DAY = availableWidth / (VISIBLE_MONTHS * 30.44);
    }

    var totalDays          = Math.ceil((timelineEnd - timelineStart) / 86400000);
    var totalTimelineWidth = totalDays * PIXELS_PER_DAY;
    rmTotalTimelineWidth   = totalTimelineWidth;

    // Compute the left edge for bars with no start date.
    // Cap at the earliest known start date, but go back at least to last month.
    var lastMonthDate = new Date(today.getFullYear(), today.getMonth() - 1, 1);
    var lastMonthPx   = Math.max(0, Math.floor((lastMonthDate - timelineStart) / 86400000) * PIXELS_PER_DAY);
    var minStartDate  = null;
    for (var si = 0; si < data.initiatives.length; si++) {
        var sInit = data.initiatives[si];
        if (sInit.start_date) {
            var sd = new Date(sInit.start_date + 'T00:00:00');
            if (!minStartDate || sd < minStartDate) minStartDate = sd;
        }
        for (var se = 0; se < sInit.epics.length; se++) {
            if (sInit.epics[se].start_date) {
                var ed = new Date(sInit.epics[se].start_date + 'T00:00:00');
                if (!minStartDate || ed < minStartDate) minStartDate = ed;
            }
        }
    }
    var minStartPx = minStartDate
        ? Math.floor((minStartDate - timelineStart) / 86400000) * PIXELS_PER_DAY
        : lastMonthPx;
    rmNoDateLeft = Math.min(minStartPx, lastMonthPx);

    var html = '';

    // ── Sticky wrapper: nav + column header stick together when scrolling ────────
    html += '<div class="rm-sticky-top">';

    html += '<div class="rm-nav">';
    html += '<button class="rm-nav-btn" id="rm-nav-prev" type="button">&#8249;</button>';
    html += '<span class="rm-nav-label" id="rm-nav-label"></span>';
    html += '<button class="rm-nav-btn" id="rm-nav-next" type="button">&#8250;</button>';
    var projectNames = data.project_names || {};
    html += '<div class="rm-filter-group" data-filter-type="initiative">';
    html += '<button type="button" class="rm-filter-btn">Initiatives &#9662;</button>';
    html += '<div class="rm-filter-dropdown" style="display:none">' + buildFilterDropdownHtml(initProjects, projectNames) + '</div>';
    html += '</div>';
    html += '<div class="rm-filter-group" data-filter-type="epic">';
    html += '<button type="button" class="rm-filter-btn">Epics &#9662;</button>';
    html += '<div class="rm-filter-dropdown" style="display:none">' + buildFilterDropdownHtml(epicProjects, projectNames) + '</div>';
    html += '</div>';
    html += '<button type="button" class="rm-filter-btn rm-deps-toggle" id="rm-deps-toggle">Dependencies</button>';
    html += '</div>';

    html += '<div class="rm-header">';
    html += '<div class="rm-project-col rm-header-label">Project</div>';
    html += '<div class="rm-label-col rm-header-label">Initiative / Epic</div>';
    html += '<div class="rm-header-status">Status</div>';
    html += '<div class="rm-header-timeline">';
    html += '<div class="rm-months" id="rm-months-inner" style="width:' + totalTimelineWidth + 'px">';
    for (var i = 0; i < months.length; i++) {
        var m     = months[i];
        var nextM = new Date(m.getFullYear(), m.getMonth() + 1, 1);
        var mLeft  = Math.floor((m     - timelineStart) / 86400000) * PIXELS_PER_DAY;
        var mWidth = Math.floor((nextM - m)             / 86400000) * PIXELS_PER_DAY;
        html += '<div class="rm-month" style="left:' + mLeft + 'px;width:' + mWidth + 'px">';
        html += monthName(m) + ' ' + m.getFullYear();
        html += '</div>';
    }
    html += '</div>'; // rm-months
    html += '</div>'; // rm-header-timeline
    html += '</div>'; // rm-header
    html += '</div>'; // rm-sticky-top

    // ── Scrollable body ───────────────────────────────────────────────────────
    html += '<div class="rm-outer" id="rm-outer">';
    html += '<div class="rm-inner" style="width:' + (PROJECT_COL_WIDTH + LABEL_WIDTH + STATUS_COL_WIDTH + totalTimelineWidth) + 'px">';
    html += '<div class="rm-body">';

    // Gridlines + today line
    html += '<div class="rm-gridlines">';
    for (var i = 0; i < months.length; i++) {
        var gLeft = PROJECT_COL_WIDTH + LABEL_WIDTH + STATUS_COL_WIDTH + Math.floor((months[i] - timelineStart) / 86400000) * PIXELS_PER_DAY;
        html += '<div class="rm-gridline" style="left:' + gLeft + 'px"></div>';
    }
    if (today >= timelineStart && today <= timelineEnd) {
        var todayLeft = PROJECT_COL_WIDTH + LABEL_WIDTH + STATUS_COL_WIDTH + Math.floor((today - timelineStart) / 86400000) * PIXELS_PER_DAY;
        html += '<div class="rm-today-line" style="left:' + todayLeft + 'px"></div>';
    }
    html += '</div>'; // rm-gridlines

    // Initiative + epic rows
    for (var idx = 0; idx < data.initiatives.length; idx++) {
        var init   = data.initiatives[idx];
        var initId = 'rm-init-' + idx;
        var initProjKey  = init.key.split('-')[0];
        var initProjName = projectNames[initProjKey] || initProjKey;
        html += '<div class="rm-row rm-init-row" data-toggle="' + initId + '" data-status-category="' + escAttr(init.status_category) + '" data-item-key="' + escAttr(init.key) + '" data-project="' + escAttr(initProjKey) + '">';
        html += '<div class="rm-project-col" title="' + escAttr(initProjName) + '">' + escHtml(initProjName) + '</div>';
        html += '<div class="rm-label-col">';
        html += '<span class="rm-expand-icon" id="icon-' + initId + '">&#9654;</span>';
        html += '<a href="' + escHtml(init.url) + '" target="_blank" class="rm-title-link" title="' + escAttr(init.title) + '">' + escHtml(init.title) + '</a>';
        html += '</div>';
        html += '<div class="rm-status-col">' + renderStatusBadge(init.status, init.status_category) + '</div>';
        var doneEpics = 0, cancelledEpics = 0, inprogressEpics = 0;
        for (var e = 0; e < init.epics.length; e++) {
            var esc = init.epics[e].status_category;
            if (esc === 'done') doneEpics++;
            else if (esc === 'cancelled') cancelledEpics++;
            else if (esc === 'indeterminate') inprogressEpics++;
        }
        var initChildren = init.epics.length > 0
            ? { done: doneEpics, cancelled: cancelledEpics, inprogress: inprogressEpics,
                todo: init.epics.length - doneEpics - cancelledEpics - inprogressEpics,
                total: init.epics.length, label: 'Epics' }
            : null;

        html += '<div class="rm-timeline-col" style="width:' + totalTimelineWidth + 'px">';
        html += renderBar(init, timelineStart, initChildren);
        html += '</div>';
        html += '</div>';

        for (var j = 0; j < init.epics.length; j++) {
            var epic     = init.epics[j];
            var epicProjKey  = epic.key.split('-')[0];
            var epicProjName = projectNames[epicProjKey] || epicProjKey;
            html += '<div class="rm-row rm-epic-row ' + initId + '" data-status-category="' + escAttr(epic.status_category) + '" data-item-key="' + escAttr(epic.key) + '" data-project="' + escAttr(epicProjKey) + '" style="display:none">';
            html += '<div class="rm-project-col rm-project-col-epic" title="' + escAttr(epicProjName) + '">' + escHtml(epicProjName) + '</div>';
            html += '<div class="rm-label-col rm-epic-label">';
            html += '<a href="' + escHtml(epic.url) + '" target="_blank" class="rm-title-link" title="' + escAttr(epic.title) + '">' + escHtml(epic.title) + '</a>';
            html += '</div>';
            html += '<div class="rm-status-col">' + renderStatusBadge(epic.status, epic.status_category) + '</div>';
            var epicCancelled  = epic.cancelled_stories  || 0;
            var epicInprogress = epic.inprogress_stories || 0;
            var epicChildren = epic.total_stories > 0
                ? { done: epic.done_stories, cancelled: epicCancelled, inprogress: epicInprogress,
                    todo: Math.max(0, epic.total_stories - epic.done_stories - epicCancelled - epicInprogress),
                    total: epic.total_stories, label: 'Stories' }
                : null;

            html += '<div class="rm-timeline-col" style="width:' + totalTimelineWidth + 'px">';
            html += renderBar(epic, timelineStart, epicChildren);
            html += '</div>';
            html += '</div>';
        }
    }

    html += '<svg id="rm-deps-svg" class="rm-deps-svg"></svg>';
    html += '</div>'; // rm-body
    html += '</div>'; // rm-inner
    html += '</div>'; // rm-outer

    container.innerHTML = html;

    rmOuter = document.getElementById('rm-outer');

    // Dependency arrow drawing — captured in a closure so other handlers can call it
    rmRedrawArrows = function() { drawDependencyArrows(data, container); };

    // Dependencies toggle button
    var depsToggle = document.getElementById('rm-deps-toggle');
    if (depsToggle) {
        depsToggle.addEventListener('click', function() {
            rmShowDeps = !rmShowDeps;
            this.classList.toggle('rm-deps-toggle-on', rmShowDeps);
            rmRedrawArrows();
        });
    }

    // Sync month header with body scroll (trackpad / touch / programmatic)
    rmOuter.addEventListener('scroll', function() {
        syncMonthHeader(rmOuter.scrollLeft);
        updateNavLabelFromScroll();
        updateNavButtons();
    });

    // Nav buttons
    document.getElementById('rm-nav-prev').addEventListener('click', function() { rmNavigate(-1); });
    document.getElementById('rm-nav-next').addEventListener('click', function() { rmNavigate(1);  });

    // Drag-to-scroll on the timeline
    var isDragging = false, didDrag = false, dragStartX = 0, dragStartScroll = 0;

    rmOuter.addEventListener('mousedown', function(e) {
        if (e.button !== 0) return;
        isDragging = true;
        didDrag    = false;
        dragStartX      = e.clientX;
        dragStartScroll = rmOuter.scrollLeft;
    });

    window.addEventListener('mousemove', function(e) {
        if (!isDragging) return;
        var dx = e.clientX - dragStartX;
        if (Math.abs(dx) > 4) {
            didDrag = true;
            rmOuter.classList.add('rm-dragging');
        }
        rmOuter.scrollLeft = dragStartScroll - dx;
        syncMonthHeader(rmOuter.scrollLeft);
        updateNavLabelFromScroll();
        updateNavButtons();
    });

    window.addEventListener('mouseup', function() {
        isDragging = false;
        rmOuter.classList.remove('rm-dragging');
    });

    // Suppress the click that fires after a drag so links/rows don't activate
    rmOuter.addEventListener('click', function(e) {
        if (didDrag) {
            e.stopPropagation();
            e.preventDefault();
            didDrag = false;
        }
    }, true);

    // Touch drag
    var touchStartX = 0, touchStartScroll = 0;
    rmOuter.addEventListener('touchstart', function(e) {
        touchStartX      = e.touches[0].clientX;
        touchStartScroll = rmOuter.scrollLeft;
    }, { passive: true });
    rmOuter.addEventListener('touchmove', function(e) {
        var dx = e.touches[0].clientX - touchStartX;
        rmOuter.scrollLeft = touchStartScroll - dx;
        syncMonthHeader(rmOuter.scrollLeft);
        updateNavLabelFromScroll();
        updateNavButtons();
    }, { passive: true });

    // Initial scroll: 1 month before the current month
    var initViewStart = new Date(today.getFullYear(), today.getMonth() - 1, 1);
    var minViewStart  = new Date(timelineStart.getFullYear(), timelineStart.getMonth(), 1);
    if (initViewStart < minViewStart) initViewStart = minViewStart;
    rmViewStart = initViewStart;
    var initScroll = Math.max(0, Math.floor((initViewStart - timelineStart) / 86400000) * PIXELS_PER_DAY);
    rmOuter.scrollLeft = initScroll;
    syncMonthHeader(initScroll);
    updateNavLabel();
    updateNavButtons();

    // Expand / collapse
    var initRows = container.querySelectorAll('.rm-init-row');
    for (var i = 0; i < initRows.length; i++) {
        initRows[i].addEventListener('click', function(e) {
            if (e.target.tagName === 'A') return;
            var toggleId = this.getAttribute('data-toggle');
            expanded[toggleId] = !expanded[toggleId];
            var icon = document.getElementById('icon-' + toggleId);
            if (icon) icon.innerHTML = expanded[toggleId] ? '&#9660;' : '&#9654;';
            setEpicRowsVisibility(container, toggleId);
            if (rmRedrawArrows) rmRedrawArrows();
        });
    }

    // Status filter dropdowns
    var filterGroups = container.querySelectorAll('.rm-filter-group');
    for (var i = 0; i < filterGroups.length; i++) {
        (function(group) {
            var isInit   = group.getAttribute('data-filter-type') === 'initiative';
            var btn      = group.querySelector('.rm-filter-btn');
            var dropdown = group.querySelector('.rm-filter-dropdown');

            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                var wasOpen = dropdown.style.display !== 'none';
                var allDDs  = container.querySelectorAll('.rm-filter-dropdown');
                for (var j = 0; j < allDDs.length; j++) allDDs[j].style.display = 'none';
                if (!wasOpen) dropdown.style.display = '';
            });

            dropdown.addEventListener('click', function(e) { e.stopPropagation(); });

            var checkboxes = group.querySelectorAll('input[type="checkbox"]');
            for (var j = 0; j < checkboxes.length; j++) {
                checkboxes[j].addEventListener('change', function() {
                    var filterKind = this.getAttribute('data-filter');
                    if (filterKind === 'project') {
                        if (isInit) {
                            hiddenInitProjects[this.value] = !this.checked;
                        } else {
                            hiddenEpicProjects[this.value] = !this.checked;
                        }
                    } else {
                        if (isInit) {
                            hiddenInitCategories[this.value] = !this.checked;
                        } else {
                            hiddenEpicCategories[this.value] = !this.checked;
                        }
                    }
                    applyFilters(container);
                });
            }
        })(filterGroups[i]);
    }

    // Close dropdowns when clicking outside
    document.addEventListener('click', function() {
        var allDDs = container.querySelectorAll('.rm-filter-dropdown');
        for (var j = 0; j < allDDs.length; j++) allDDs[j].style.display = 'none';
    });

    applyFilters(container);  // also calls rmRedrawArrows via its own tail-call
}

// ── Navigation ────────────────────────────────────────────────────────────────

function rmNavigate(direction) {
    rmViewStart = new Date(rmViewStart.getFullYear(), rmViewStart.getMonth() + direction, 1);
    var scrollLeft = Math.max(0, Math.floor((rmViewStart - rmTimelineStart) / 86400000) * PIXELS_PER_DAY);
    rmOuter.scrollLeft = scrollLeft;
    syncMonthHeader(scrollLeft);
    updateNavLabel();
    updateNavButtons();
}

function updateNavButtons() {
    var prevBtn = document.getElementById('rm-nav-prev');
    var nextBtn = document.getElementById('rm-nav-next');
    if (!prevBtn || !nextBtn || !rmOuter) return;
    prevBtn.disabled = rmOuter.scrollLeft <= 0;
    nextBtn.disabled = rmOuter.scrollLeft >= rmOuter.scrollWidth - rmOuter.clientWidth - 1;
}

function syncMonthHeader(scrollLeft) {
    var el = document.getElementById('rm-months-inner');
    if (el) el.style.transform = 'translateX(-' + scrollLeft + 'px)';
}

function updateNavLabel() {
    var label = document.getElementById('rm-nav-label');
    if (!label || !rmViewStart) return;
    var vs = new Date(rmViewStart.getFullYear(), rmViewStart.getMonth(), 1);
    var ve = new Date(vs.getFullYear(), vs.getMonth() + VIEW_MONTHS - 1, 1);
    label.textContent = monthName(vs) + ' ' + vs.getFullYear() + ' \u2013 ' + monthName(ve) + ' ' + ve.getFullYear();
}

function updateNavLabelFromScroll() {
    if (!rmTimelineStart || !rmOuter) return;
    var daysFromStart = rmOuter.scrollLeft / PIXELS_PER_DAY;
    var d = new Date(rmTimelineStart.getTime() + daysFromStart * 86400000);
    rmViewStart = new Date(d.getFullYear(), d.getMonth(), 1);
    updateNavLabel();
}

// ── Status category filter ────────────────────────────────────────────────────

function anyEpicPassesFilter(container, initId) {
    var epicRows = container.querySelectorAll('.' + initId);
    if (epicRows.length === 0) return true;  // no epics — initiative stands on its own
    for (var k = 0; k < epicRows.length; k++) {
        var cat  = epicRows[k].getAttribute('data-status-category');
        var proj = epicRows[k].getAttribute('data-project');
        if (!hiddenEpicCategories[cat] && !hiddenEpicProjects[proj]) return true;
    }
    return false;
}

function setEpicRowsVisibility(container, initId, initHidden) {
    var epicRows = container.querySelectorAll('.' + initId);
    for (var k = 0; k < epicRows.length; k++) {
        var row  = epicRows[k];
        var cat  = row.getAttribute('data-status-category');
        var proj = row.getAttribute('data-project');
        // Initiative filter takes precedence: if init is hidden, epics are hidden too
        var visible = !initHidden && expanded[initId] && !hiddenEpicCategories[cat] && !hiddenEpicProjects[proj];
        row.style.display = visible ? '' : 'none';
    }
}

function applyFilters(container) {
    var initRows = container.querySelectorAll('.rm-init-row');
    for (var i = 0; i < initRows.length; i++) {
        var row    = initRows[i];
        var cat    = row.getAttribute('data-status-category');
        var proj   = row.getAttribute('data-project');
        var initId = row.getAttribute('data-toggle');
        var ownHidden      = !!(hiddenInitCategories[cat] || hiddenInitProjects[proj]);
        var noEpicsVisible = initId && !anyEpicPassesFilter(container, initId);
        var initHidden     = ownHidden || noEpicsVisible;
        row.style.display = initHidden ? 'none' : '';
        if (initId) setEpicRowsVisibility(container, initId, initHidden);
    }
    if (rmRedrawArrows) rmRedrawArrows();
}

// ── Rendering helpers ─────────────────────────────────────────────────────────

function renderStatusBadge(status, statusCategory) {
    var color = STATUS_COLORS[statusCategory] || STATUS_COLORS['new'];
    return '<span class="rm-status-badge" style="background:' + color + '" title="' + escAttr(status) + '">' + escHtml(status) + '</span>';
}

function renderBar(item, timelineStart, children) {
    var isInProgress = item.status_category === 'indeterminate';
    var hasStart     = !!item.start_date;
    var hasEnd       = !!item.end_date;

    // Items with no dates at all and not in progress keep the "No dates" label
    if (!hasStart && !hasEnd && !isInProgress) {
        return '<div class="rm-no-dates">No dates</div>';
    }

    // Compute pixel position; missing edges extend to the full timeline boundary.
    var left, rightPx;
    if (hasStart) {
        var start = new Date(item.start_date + 'T00:00:00');
        left = Math.floor((start - timelineStart) / 86400000) * PIXELS_PER_DAY;
    } else {
        left = rmNoDateLeft;
    }
    if (hasEnd) {
        var end = new Date(item.end_date + 'T00:00:00');
        rightPx = Math.floor((end - timelineStart) / 86400000) * PIXELS_PER_DAY;
    } else {
        rightPx = rmTotalTimelineWidth;
    }
    var width = Math.max(rightPx - left, 4);

    var bg;
    if (children && children.total > 0) {
        var t            = children.total;
        var donePct      = Math.round(children.done       / t * 100);
        var cancelledPct = Math.round(children.cancelled  / t * 100);
        var inpPct       = Math.round(children.inprogress / t * 100);
        // Clamp to avoid rounding overflow
        if (donePct + cancelledPct > 100) cancelledPct = 100 - donePct;
        if (donePct + cancelledPct + inpPct > 100) inpPct = 100 - donePct - cancelledPct;
        var p1 = donePct;
        var p2 = p1 + cancelledPct;
        var p3 = p2 + inpPct;
        bg = 'linear-gradient(to right,' +
            '#2da44e 0%,#2da44e ' + p1 + '%,' +
            '#9e3e3e ' + p1 + '%,#9e3e3e ' + p2 + '%,' +
            '#0969da ' + p2 + '%,#0969da ' + p3 + '%,' +
            '#8b949e ' + p3 + '%,#8b949e 100%)';
    } else {
        bg = STATUS_COLORS[item.status_category] || STATUS_COLORS['new'];
    }

    var tooltip = item.key + ': ' + item.title +
        '\nStatus: ' + item.status +
        '\nStart: '  + (item.start_date || '(open)') +
        '\nEnd: '    + (item.end_date   || '(open)');
    if (children && children.total > 0) {
        var parts = [];
        if (children.done)       parts.push(children.done       + ' done');
        if (children.cancelled)  parts.push(children.cancelled  + ' cancelled');
        if (children.inprogress) parts.push(children.inprogress + ' in progress');
        if (children.todo)       parts.push(children.todo       + ' to do');
        tooltip += '\n' + children.label + ': ' + parts.join(', ');
    }

    var style = 'left:' + left + 'px;width:' + width + 'px;background:' + bg;

    // Apply a gradient mask to fade out open (undated) edges
    if (!hasStart || !hasEnd) {
        var fadeSize  = 20;
        var maskStops = [];
        if (!hasStart) {
            maskStops.push('transparent 0%', 'black ' + fadeSize + 'px');
        } else {
            maskStops.push('black 0%');
        }
        if (!hasEnd) {
            maskStops.push('black calc(100% - ' + fadeSize + 'px)', 'transparent 100%');
        } else {
            maskStops.push('black 100%');
        }
        var mask = 'linear-gradient(to right,' + maskStops.join(',') + ')';
        style += ';-webkit-mask-image:' + mask + ';mask-image:' + mask;
    }

    return '<div class="rm-bar" style="' + style + '" title="' + escAttr(tooltip) + '"></div>';
}

// ── Dependency arrows ─────────────────────────────────────────────────────────

function drawDependencyArrows(data, container) {
    var svg  = document.getElementById('rm-deps-svg');
    var body = container.querySelector('.rm-body');
    if (!svg || !body) return;

    if (!rmShowDeps) { svg.innerHTML = ''; return; }

    var allDeps = (data.initiative_deps || []).concat(data.epic_deps || []);
    if (!allDeps.length) { svg.innerHTML = ''; return; }

    // Size SVG to cover the full scrollable body area
    svg.setAttribute('width',  PROJECT_COL_WIDTH + LABEL_WIDTH + STATUS_COL_WIDTH + rmTotalTimelineWidth);
    svg.setAttribute('height', body.offsetHeight);

    // Build key → row element lookup
    var keyToRow = {};
    var rows = body.querySelectorAll('.rm-row[data-item-key]');
    for (var i = 0; i < rows.length; i++) {
        keyToRow[rows[i].getAttribute('data-item-key')] = rows[i];
    }

    var defs =
        '<defs>' +
        '<marker id="rm-arrowhead" markerWidth="7" markerHeight="7"' +
        ' refX="6" refY="3.5" orient="auto">' +
        '<path d="M0,0.5 L0,6.5 L6,3.5 z" fill="rgba(100,100,100,0.75)"/>' +
        '</marker>' +
        '</defs>';

    var paths = '';
    var BAR_CENTER_Y = 6 + 10;  // bar top-offset + half bar height

    for (var i = 0; i < allDeps.length; i++) {
        var fromKey = allDeps[i][0];
        var toKey   = allDeps[i][1];

        var fromRow = keyToRow[fromKey];
        var toRow   = keyToRow[toKey];
        if (!fromRow || !toRow) continue;
        if (fromRow.style.display === 'none' || toRow.style.display === 'none') continue;

        var fromBar = fromRow.querySelector('.rm-bar');
        var toBar   = toRow.querySelector('.rm-bar');
        if (!fromBar || !toBar) continue;

        var fromLeft  = parseFloat(fromBar.style.left)  || 0;
        var fromWidth = parseFloat(fromBar.style.width) || 0;
        var toLeft    = parseFloat(toBar.style.left)    || 0;

        // Coordinates relative to .rm-body
        var x1 = PROJECT_COL_WIDTH + LABEL_WIDTH + STATUS_COL_WIDTH + fromLeft + fromWidth;
        var y1 = fromRow.offsetTop + BAR_CENTER_Y;
        var x2 = PROJECT_COL_WIDTH + LABEL_WIDTH + STATUS_COL_WIDTH + toLeft;
        var y2 = toRow.offsetTop + BAR_CENTER_Y;

        // Smooth cubic bezier; control point offset scales with horizontal distance
        var cp = Math.max(30, Math.abs(x2 - x1) * 0.4);
        var d  = 'M' + x1 + ',' + y1 +
                 ' C' + (x1 + cp) + ',' + y1 +
                 ' ' + (x2 - cp) + ',' + y2 +
                 ' ' + x2 + ',' + y2;

        paths += '<path d="' + d + '"' +
                 ' stroke="rgba(100,100,100,0.65)"' +
                 ' stroke-width="1.5"' +
                 ' fill="none"' +
                 ' marker-end="url(#rm-arrowhead)"/>';
    }

    svg.innerHTML = defs + paths;
}

function monthName(d) {
    return ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][d.getMonth()];
}

function escHtml(str) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str || ''));
    return div.innerHTML;
}

function escAttr(str) {
    return (str || '').replace(/&/g,'&amp;').replace(/"/g,'&quot;')
        .replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
