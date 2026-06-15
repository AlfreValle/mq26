# Fuentes locales — MQ26

Colocar aquí el archivo `Inter.woff2` para eliminar la dependencia de Google Fonts.

## Cómo obtenerlo

1. Ir a https://fonts.google.com/specimen/Inter
2. Descargar la familia completa
3. Copiar `Inter-Regular.woff2`, `Inter-SemiBold.woff2`, `Inter-Bold.woff2` en esta carpeta
4. Renombrar el principal a `Inter.woff2`

## Alternativa automática

```bash
pip install fonttools
python -c "
import urllib.request
url = 'https://fonts.gstatic.com/s/inter/v13/UcCO3FwrK3iLTeHuS_fvQtMwCp50KnMw2boKoduKmMEVuLyfAZ9hiJ-Ek-_EeA.woff2'
urllib.request.urlretrieve(url, 'Inter.woff2')
print('Inter.woff2 descargada')
"
```

Si el archivo no existe, el CSS cae automáticamente al CDN de Google Fonts (fallback).
