$.extend({
    keys:	 function(obj){
        var a = [];
        $.each(obj, function(k){ a.push(k); });
        return a;
    }
});

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

// LOAD PLAYLIST RESULTS
function injectPlaylist(json) {
    $("#results").spin();
    $("#spacer").height(0);
    keys = $.keys(json.playlist);
    var results = "";
    var plist = "";
    
    var results_txt = document.getElementById("results");

    $("#status").html("<a href="+json.playlist_urn+">Open in Spotify!</a>").show().fadeIn(1000);
    results += "<ul>";
    for (i=0; i<keys.length; i++) {
        key = keys[i];
        val = json.playlist[key];
        
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