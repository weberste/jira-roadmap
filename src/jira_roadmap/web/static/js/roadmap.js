/**
 * Roadmap timeline rendering.
 * Pure HTML/CSS/JS — no extra libraries.
 */

var STATUS_COLORS = {
    'new': '#8b949e',           // gray  (To Do)
    'indeterminate': '#0969da', // blue  (In Progress)
    'done': '#2da44e'           // green (Done)
};

// Light tints of each status color, used for the "not yet done" portion of the progress bar
var STATUS_COLORS_LIGHT = {
    'new': '#d0d7de',
    'indeterminate': '#cce0ff',
    'done': '#aceebb'
};

var PIXELS_PER_DAY   = 4;    // overridden at init based on container width
var LABEL_WIDTH      = 300;
var STATUS_COL_WIDTH = 120;
var VIEW_MONTHS      = 11;   // months shown in nav label (1 past + current + 9 future)
var VISIBLE_MONTHS   = 11;   // months that should fill the visible timeline area

// Status categories hidden per row type. Default: hide "done" (Done + Cancelled).
var hiddenInitCategories = { 'done': true };
var hiddenEpicCategories = { 'done': true };
var expanded = {};

// State shared between init and nav helpers
var rmOuter         = null;
var rmTimelineStart = null;
var rmViewStart     = null;  // first-of-month date at the left edge of the visible window

function initRoadmap(data) {
    var container = document.getElementById('roadmap-timeline');
    if (!container || !data || !data.initiatives.length) return;

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
    var availableWidth = container.clientWidth - LABEL_WIDTH - STATUS_COL_WIDTH;
    if (availableWidth > 0) {
        PIXELS_PER_DAY = availableWidth / (VISIBLE_MONTHS * 30.44);
    }

    var totalDays          = Math.ceil((timelineEnd - timelineStart) / 86400000);
    var totalTimelineWidth = totalDays * PIXELS_PER_DAY;

    var html = '';

    // ── Sticky wrapper: nav + column header stick together when scrolling ────────
    html += '<div class="rm-sticky-top">';

    html += '<div class="rm-nav">';
    html += '<button class="rm-nav-btn" id="rm-nav-prev" type="button">&#8249;</button>';
    html += '<span class="rm-nav-label" id="rm-nav-label"></span>';
    html += '<button class="rm-nav-btn" id="rm-nav-next" type="button">&#8250;</button>';
    html += '<div class="rm-filter-group" data-filter-type="initiative">';
    html += '<button type="button" class="rm-filter-btn">Initiatives &#9662;</button>';
    html += '<div class="rm-filter-dropdown" style="display:none">';
    html += '<label class="rm-filter-opt"><span class="rm-filter-dot" style="background:#8b949e"></span><input type="checkbox" value="new" checked> To Do</label>';
    html += '<label class="rm-filter-opt"><span class="rm-filter-dot" style="background:#0969da"></span><input type="checkbox" value="indeterminate" checked> In Progress</label>';
    html += '<label class="rm-filter-opt"><span class="rm-filter-dot" style="background:#2da44e"></span><input type="checkbox" value="done"> Done</label>';
    html += '</div>';
    html += '</div>';
    html += '<div class="rm-filter-group" data-filter-type="epic">';
    html += '<button type="button" class="rm-filter-btn">Epics &#9662;</button>';
    html += '<div class="rm-filter-dropdown" style="display:none">';
    html += '<label class="rm-filter-opt"><span class="rm-filter-dot" style="background:#8b949e"></span><input type="checkbox" value="new" checked> To Do</label>';
    html += '<label class="rm-filter-opt"><span class="rm-filter-dot" style="background:#0969da"></span><input type="checkbox" value="indeterminate" checked> In Progress</label>';
    html += '<label class="rm-filter-opt"><span class="rm-filter-dot" style="background:#2da44e"></span><input type="checkbox" value="done"> Done</label>';
    html += '</div>';
    html += '</div>';
    html += '</div>';

    html += '<div class="rm-header">';
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
    html += '<div class="rm-inner" style="width:' + (LABEL_WIDTH + STATUS_COL_WIDTH + totalTimelineWidth) + 'px">';
    html += '<div class="rm-body">';

    // Gridlines + today line
    html += '<div class="rm-gridlines">';
    for (var i = 0; i < months.length; i++) {
        var gLeft = LABEL_WIDTH + STATUS_COL_WIDTH + Math.floor((months[i] - timelineStart) / 86400000) * PIXELS_PER_DAY;
        html += '<div class="rm-gridline" style="left:' + gLeft + 'px"></div>';
    }
    var today = new Date();
    today.setHours(0, 0, 0, 0);
    if (today >= timelineStart && today <= timelineEnd) {
        var todayLeft = LABEL_WIDTH + STATUS_COL_WIDTH + Math.floor((today - timelineStart) / 86400000) * PIXELS_PER_DAY;
        html += '<div class="rm-today-line" style="left:' + todayLeft + 'px"></div>';
    }
    html += '</div>'; // rm-gridlines

    // Initiative + epic rows
    for (var idx = 0; idx < data.initiatives.length; idx++) {
        var init   = data.initiatives[idx];
        var initId = 'rm-init-' + idx;
        html += '<div class="rm-row rm-init-row" data-toggle="' + initId + '" data-status-category="' + escAttr(init.status_category) + '">';
        html += '<div class="rm-label-col">';
        html += '<span class="rm-expand-icon" id="icon-' + initId + '">&#9654;</span>';
        html += '<a href="' + escHtml(init.url) + '" target="_blank" class="rm-title-link" title="' + escAttr(init.title) + '">' + escHtml(init.title) + '</a>';
        html += '</div>';
        html += '<div class="rm-status-col">' + renderStatusBadge(init.status, init.status_category) + '</div>';
        var doneEpics = 0;
        for (var e = 0; e < init.epics.length; e++) {
            if (init.epics[e].status_category === 'done') doneEpics++;
        }
        var progressPct = init.epics.length > 0 ? Math.round(doneEpics / init.epics.length * 100) : null;

        html += '<div class="rm-timeline-col" style="width:' + totalTimelineWidth + 'px">';
        html += renderBar(init, timelineStart, progressPct);
        html += '</div>';
        html += '</div>';

        for (var j = 0; j < init.epics.length; j++) {
            var epic     = init.epics[j];
            html += '<div class="rm-row rm-epic-row ' + initId + '" data-status-category="' + escAttr(epic.status_category) + '" style="display:none">';
            html += '<div class="rm-label-col rm-epic-label">';
            html += '<a href="' + escHtml(epic.url) + '" target="_blank" class="rm-title-link" title="' + escAttr(epic.title) + '">' + escHtml(epic.title) + '</a>';
            html += '</div>';
            html += '<div class="rm-status-col">' + renderStatusBadge(epic.status, epic.status_category) + '</div>';
            var epicProgressPct = epic.total_stories > 0
                ? Math.round(epic.done_stories / epic.total_stories * 100)
                : null;

            html += '<div class="rm-timeline-col" style="width:' + totalTimelineWidth + 'px">';
            html += renderBar(epic, timelineStart, epicProgressPct);
            html += '</div>';
            html += '</div>';
        }
    }

    html += '</div>'; // rm-body
    html += '</div>'; // rm-inner
    html += '</div>'; // rm-outer

    container.innerHTML = html;

    rmOuter = document.getElementById('rm-outer');

    // Sync month header with body scroll (trackpad / touch / programmatic)
    rmOuter.addEventListener('scroll', function() {
        syncMonthHeader(rmOuter.scrollLeft);
        updateNavLabelFromScroll();
        updateNavButtons();
    });

    // Nav buttons
    document.getElementById('rm-nav-prev').addEventListener('click', function() { rmNavigate(-1); });
    document.getElementById('rm-nav-next').addEventListener('click', function() { rmNavigate(1);  });

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
                    if (isInit) {
                        hiddenInitCategories[this.value] = !this.checked;
                    } else {
                        hiddenEpicCategories[this.value] = !this.checked;
                    }
                    applyStatusFilter(container);
                });
            }
        })(filterGroups[i]);
    }

    // Close dropdowns when clicking outside
    document.addEventListener('click', function() {
        var allDDs = container.querySelectorAll('.rm-filter-dropdown');
        for (var j = 0; j < allDDs.length; j++) allDDs[j].style.display = 'none';
    });

    applyStatusFilter(container);
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

function setEpicRowsVisibility(container, initId) {
    var epicRows = container.querySelectorAll('.' + initId);
    for (var k = 0; k < epicRows.length; k++) {
        var row = epicRows[k];
        var cat = row.getAttribute('data-status-category');
        row.style.display = (expanded[initId] && !hiddenEpicCategories[cat]) ? '' : 'none';
    }
}

function applyStatusFilter(container) {
    var initRows = container.querySelectorAll('.rm-init-row');
    for (var i = 0; i < initRows.length; i++) {
        var row    = initRows[i];
        var cat    = row.getAttribute('data-status-category');
        row.style.display = hiddenInitCategories[cat] ? 'none' : '';
        var initId = row.getAttribute('data-toggle');
        if (initId) setEpicRowsVisibility(container, initId);
    }
}

// ── Rendering helpers ─────────────────────────────────────────────────────────

function renderStatusBadge(status, statusCategory) {
    var color = STATUS_COLORS[statusCategory] || STATUS_COLORS['new'];
    return '<span class="rm-status-badge" style="background:' + color + '" title="' + escAttr(status) + '">' + escHtml(status) + '</span>';
}

function renderBar(item, timelineStart, progressPct) {
    if (!item.start_date || !item.end_date) {
        return '<div class="rm-no-dates">No dates</div>';
    }
    var start = new Date(item.start_date + 'T00:00:00');
    var end   = new Date(item.end_date   + 'T00:00:00');
    var left  = Math.floor((start - timelineStart) / 86400000) * PIXELS_PER_DAY;
    var width = Math.max(Math.floor((end - start) / 86400000) * PIXELS_PER_DAY, 4);
    var color = STATUS_COLORS[item.status_category] || STATUS_COLORS['new'];

    var bg;
    if (progressPct !== null && progressPct !== undefined && progressPct > 0 && progressPct < 100) {
        var light = STATUS_COLORS_LIGHT[item.status_category] || STATUS_COLORS_LIGHT['new'];
        bg = 'linear-gradient(to right, ' + color + ' ' + progressPct + '%, ' + light + ' ' + progressPct + '%)';
    } else {
        bg = color;
    }

    var tooltip = item.key + ': ' + item.title +
        '\nStatus: ' + item.status +
        '\nStart: '  + item.start_date +
        '\nEnd: '    + item.end_date;

    return '<div class="rm-bar" style="left:' + left + 'px;width:' + width +
        'px;background:' + bg + '" title="' + escAttr(tooltip) + '"></div>';
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
