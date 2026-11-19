// Everything renders in the browser from the timetable stored on the device.
// Static routes are prerendered as empty shells so GitHub Pages can serve
// them directly; routes with parameters fall back to 404.html.
export const ssr = false;
export const prerender = true;
export const trailingSlash = 'never';
