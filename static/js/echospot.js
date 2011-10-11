$.extend({
    keys:	 function(obj){
        var a = [];
        $.each(obj, function(k){ a.push(k); });
        return a;
    }
});

function clear_container(container_name) {
    var elmt = document.getElementById(container_name);
    elmt.innerHTML="";
}

function show_spacer() {
    $("#spacer").height(200);
}
function hide_spacer() {
    $("#spacer").height(0);
}

function clear_results() {
    clear_container("results");
    clear_container("status");
    $("#searchfield").val("");
}

// DOING SHIT SPINNER
var opts = {
  lines: 12, // The number of lines to draw
  length: 17, // The length of each line
  width: 8, // The line thickness
  radius: 32, // The radius of the inner circle
  color: '#000', // #rgb or #rrggbb
  speed: 1, // Rounds per second
  trail: 60, // Afterglow percentage
  shadow: false // Whether to render a shadow
};

$.fn.spin = function(opts) {
  this.each(function() {
    var $this = $(this),
        data = $this.data();

    if (data.spinner) {
      data.spinner.stop();
      delete data.spinner;
    }
    if (opts !== false) {
      data.spinner = new Spinner($.extend({color: $this.css('color')}, opts)).spin(this);
    }
  });
  return this;
};

var history_cache = {
    // results is empty by default
    '': ""
};

// LOAD PLAYLIST RESULTS
function injectPlaylist(json) {
    $("#results").spin(); // disable results spinner, results are here
    hide_spacer(); // remove spacer div to make room for results g-style
    $.bbq.pushState( {pid:json.playlist_id} ); //
    history_cache[json.playlist_id] = json;
    $("#searchfield").val(json.query);
    
    playlist = json.playlist;
    var results = "";
    var plist = "";
    
    var results_txt = document.getElementById("results");

    $("#status").html("<a href="+json.playlist_urn+">Open in Spotify!</a>").show().fadeIn(1000);
    results += "<ul>";
    for (i=0; i<playlist.length; i++) {
        val = playlist[i];
        
        image_url = val['image'];
        artist = val['artist'];
        track = val['name'];
        track_urn = val['href'];
        artist_urn = val['artist_href'];
        
        results += '<li class="result-body">';
        // results += '<div class="loadable-image" src='+image_url+' alt=\"'+artist+'\"><\/div>';
        results += '<img class=\"thumbnail\" src='+image_url+' alt=\"'+artist+'\"><\/img>';
        results += '<span class=result-text><a href='+artist_urn+'>'+artist+'<\/a> - <a href='+track_urn+'>'+track+'<\/a></span>';
        results += '<\/li>\n';
        
        plist += track_urn+" \n";
    }
    results += "<\/ul>";
    results_txt.innerHTML=results;    
}