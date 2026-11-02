/** Build : npx tailwindcss@3 -i app/static/css/tailwind.src.css -o app/static/css/tailwind.css --minify */
module.exports = {
  darkMode: 'class',
  content: ['./app/templates/**/*.html', './app/static/js/**/*.js', './app/cvbuilder/**/*.py'],
  theme: { extend: {
    colors: { terra: { 50:'#FDF6EE',100:'#FAEBDC',200:'#F3D2B6',300:'#EAB089',400:'#E08B5A',500:'#D86730',600:'#C2532A',700:'#A04222',800:'#7E3520',900:'#5A2C19',950:'#3B1A0E' },
              cream:'#FAF1E3', brown:'#5A2C19' },
    fontFamily: { display:['Outfit','sans-serif'], sans:['Plus Jakarta Sans','system-ui','sans-serif'] } } },
};
