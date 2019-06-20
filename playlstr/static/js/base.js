String.prototype.format = String.prototype.f = function () {
    let s = this,
        i = arguments.length;

    while (i--) {
        s = s.replace(new RegExp('\\{' + i + '\\}', 'gm'), arguments[i]);
    }
    return s;
};


function createPlaylist() {
    $('#createPlaylistFail').hide();
    let location = 'http://' + window.location.host.toString() + '/';
    if (document.cookie.length === 0) createPlaylistFail();
    let playlistName = $('#newPlaylistName').val();
    $.ajax({
        type: 'POST',
        url: location + 'create/',
        headers: {'X-CSRFToken': csrfToken},
        cache: false,
        timeout: 30000,
        data: {'name': playlistName},
        error: createPlaylistFail,
        success: createPlaylistSuccess,
        dataType: 'text'
    });
}

function createPlaylistFail(data) {
    $('#createPlaylistFail').show();
}

function createPlaylistSuccess(data) {
    window.location = 'http://' + window.location.host + '/list/' + data;
}

