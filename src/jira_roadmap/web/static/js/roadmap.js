/**
 * Roadmap timeline rendering.
 * Pure HTML/CSS/JS — no extra libraries.
 */

var STATUS_COLORS = {
    'new': '#8b949e',           // gray (To Do)
    'indeterminate': '#0969da', // blue (In Progress)
    'done': '#2da44e'           // green (Done)
};

var hideDone = true;
var expanded = {};

function initRoadmap(data) {
    var container = document.getElementById('roadmap-timeline');
    if (!container || !data || !data.initiatives.length) return;

    var timelineStart = new Date(data.timeline_start + 'T00:00:00');
    var timelineEnd = new Date(data.timeline_end + 'T00:00:00');
    var totalDays = (timelineEnd - timelineStart) / (1000 * 60 * 60 * 24);
    if (totalDays <= 0) return;

    // Build months array for headers
    var months = [];
    var cursor = new Date(timelineStart);
    cursor.setDate(1);
    while (cursor < timelineEnd) {
        months.push(new Date(cursor));
        cursor.setMonth(cursor.getMonth() + 1);
    }

    // Build HTML
    var html = '';

    // Month headers
    html += '<div class="rm-header">';
    html += '<div class="rm-label-col rm-header-label">Initiative / Epic</div>';
    html += '<div class="rm-timeline-col">';
    html += '<div class="rm-months">';
    for (var i = 0; i < months.length; i++) {
        var m = months[i];
        var left = dateToPct(m, timelineStart, totalDays);
        var nextMonth = new Date(m);
        nextMonth.setMonth(nextMonth.getMonth() + 1);
        var width = dateToPct(nextMonth, timelineStart, totalDays) - left;
        html += '<div class="rm-month" style="left:' + left + '%;width:' + width + '%">';
        html += monthName(m) + ' ' + m.getFullYear();
        html += '</div>';
    }
    html += '</div>';
    html += '</div>';
    html += '</div>';

    // Rows
    html += '<div class="rm-body">';
    // Grid lines (one per month)
    html += '<div class="rm-gridlines">';
    for (var i = 0; i < months.length; i++) {
        var left = dateToPct(months[i], timelineStart, totalDays);
        html += '<div class="rm-gridline" style="left:' + left + '%"></div>';
    }
    // Today line
    var today = new Date();
    today.setHours(0, 0, 0, 0);
    if (today >= timelineStart && today <= timelineEnd) {
        var todayPct = dateToPct(today, timelineStart, totalDays);
        html += '<div class="rm-today-line" style="left:' + todayPct + '%"></div>';
    }
    html += '</div>';

    for (var idx = 0; idx < data.initiatives.length; idx++) {
        var init = data.initiatives[idx];
        var initId = 'rm-init-' + idx;
        var initDone = init.status_category === 'done';

        // Initiative row
        html += '<div class="rm-row rm-init-row" data-toggle="' + initId + '" data-done="' + initDone + '">';
        html += '<div class="rm-label-col">';
        html += '<span class="rm-expand-icon" id="icon-' + initId + '">&#9654;</span> ';
        html += '<a href="' + escHtml(init.url) + '" target="_blank" class="rm-key">' + escHtml(init.key) + '</a> ';
        html += '<span class="rm-title">' + escHtml(init.title) + '</span>';
        html += '</div>';
        html += '<div class="rm-timeline-col">';
        html += renderBar(init, timelineStart, totalDays);
        html += '</div>';
        html += '</div>';

        // Epic rows (hidden by default)
        for (var j = 0; j < init.epics.length; j++) {
            var epic = init.epics[j];
            var epicDone = epic.status_category === 'done';
            html += '<div class="rm-row rm-epic-row ' + initId + '" data-done="' + epicDone + '" style="display:none">';
            html += '<div class="rm-label-col rm-epic-label">';
            html += '<a href="' + escHtml(epic.url) + '" target="_blank" class="rm-key">' + escHtml(epic.key) + '</a> ';
            html += '<span class="rm-title">' + escHtml(epic.title) + '</span>';
            html += '</div>';
            html += '<div class="rm-timeline-col">';
            html += renderBar(epic, timelineStart, totalDays);
            html += '</div>';
            html += '</div>';
        }
    }
    html += '</div>';

    container.innerHTML = html;

    // Expand/collapse click handlers
    var initRows = container.querySelectorAll('.rm-init-row');
    for (var i = 0; i < initRows.length; i++) {
        initRows[i].addEventListener('click', function(e) {
            if (e.target.tagName === 'A') return;
            var toggleId = this.getAttribute('data-toggle');
            expanded[toggleId] = !expanded[toggleId];
            var icon = document.getElementById('icon-' + toggleId);
            if (icon) {
                icon.innerHTML = expanded[toggleId] ? '&#9660;' : '&#9654;';
            }
            setEpicRowsVisibility(container, toggleId);
        });
    }

    // Apply initial done filter
    applyDoneFilter(container);
}

function setEpicRowsVisibility(container, initId) {
    var epicRows = container.querySelectorAll('.' + initId);
    for (var k = 0; k < epicRows.length; k++) {
        var row = epicRows[k];
        var isDone = row.getAttribute('data-done') === 'true';
        row.style.display = (expanded[initId] && (!hideDone || !isDone)) ? '' : 'none';
    }
}

function applyDoneFilter(container) {
    var initRows = container.querySelectorAll('.rm-init-row');
    for (var i = 0; i < initRows.length; i++) {
        var row = initRows[i];
        var isDone = row.getAttribute('data-done') === 'true';
        if (isDone) {
            row.style.display = hideDone ? 'none' : '';
        }
        var initId = row.getAttribute('data-toggle');
        if (initId) {
            setEpicRowsVisibility(container, initId);
        }
    }
}

window.toggleDoneItems = function(show) {
    hideDone = !show;
    var container = document.getElementById('roadmap-timeline');
    if (container) applyDoneFilter(container);
};

function dateToPct(d, start, totalDays) {
    var days = (d - start) / (1000 * 60 * 60 * 24);
    return Math.max(0, Math.min(100, (days / totalDays) * 100));
}

function renderBar(item, timelineStart, totalDays) {
    if (!item.start_date || !item.end_date) {
        return '<div class="rm-no-dates">No dates</div>';
    }
    var start = new Date(item.start_date + 'T00:00:00');
    var end = new Date(item.end_date + 'T00:00:00');
    var left = dateToPct(start, timelineStart, totalDays);
    var right = dateToPct(end, timelineStart, totalDays);
    var width = Math.max(right - left, 0.5); // min width for visibility
    var color = STATUS_COLORS[item.status_category] || STATUS_COLORS['new'];

    var tooltip = item.key + ': ' + item.title +
        '\nStatus: ' + item.status +
        '\nStart: ' + item.start_date +
        '\nEnd: ' + item.end_date;

    return '<div class="rm-bar" style="left:' + left + '%;width:' + width +
        '%;background:' + color + '" title="' + escAttr(tooltip) + '"></div>';
}

function monthName(d) {
    var names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return names[d.getMonth()];
}

function escHtml(str) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str || ''));
    return div.innerHTML;
}

function escAttr(str) {
    return (str || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;')
        .replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
