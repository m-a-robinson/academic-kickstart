+++
widget = "slider"  # Use the Slider widget
headless = true  # This file represents a page section.
active = true  # Activate this widget? true/false
weight = 65  # Order that this section will appear.

# ... Put Your Section Options Here (section position etc.) ...

# Slide interval.
# Use `false` to disable animation or enter a time in ms, e.g. `5000` (5s).
interval = 3000

# Minimum slide height.
# Specify a height to ensure a consistent height for each slide.
height = "400px"

# Slides.
# Duplicate an `[[item]]` block to add more slides.
[[item]]
  title = "spm1d"
  content = "Statistical Parametric Mapping and waveform analysis"
  align = "center"  # Choose `center`, `left`, or `right`.
  overlay_color = "#404040"  # An HTML color value. Optional
  overlay_img = "slider/spm1d.png"  # relative to `static/img/`
  overlay_filter = 0.4  # Darken the image. Value in range 0-1.
  cta_label = "project details"
  cta_url = "#spm1d_papers"
  cta_icon_pack = "fas"
  cta_icon = "book-reader"

  # Call to action button (optional).
  #   Activate the button by specifying a URL and button label below.
  #   Deactivate by commenting out parameters, prefixing lines with `#`.
  #cta_label = "Get Academic"
  #cta_url = "https://sourcethemes.com/academic/"
  #cta_icon_pack = "fas"
  #cta_icon = "graduation-cap"

[[item]]
  title = "knee biomechanics"
  content = "ACL injury, sidestepping, neuromuscular risk factors"
  align = "center"
  overlay_color = "#404040"  # An HTML color value.
  overlay_img = "slider/knee.png"  # relative to `static/img/` folder.
  overlay_filter = 0.1  # Darken the image. Value in range 0-1.
  cta_label = "project details"
  cta_url = "https://arxiv.org/abs/2002.12335"
  cta_icon_pack = "fas"
  cta_icon = "book-reader"


[[item]]
  title = "training load"
  content = "Integrating biomechanics into training load monitoring"
  align = "center"
  overlay_color = "#404040"  # An HTML color value.
  overlay_img = "slider/grf_predict.png"  # relative to `static/img/` folder.
  overlay_filter = 0.4  # Darken the image. Value in range 0-1.
  cta_label = "project details"
  cta_url = "https://arxiv.org/abs/2002.12335"
  cta_icon_pack = "fas"
  cta_icon = "book-reader"


+++
