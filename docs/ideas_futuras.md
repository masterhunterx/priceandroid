# Ideas y Referencias para el Futuro — FreshCart KAIROS

---

## Android CLI — Build Android apps 3x más rápido con agentes IA

**URL:** https://android-developers.googleblog.com/2026/04/build-android-apps-3x-faster-using-any-agent.html  
**Fecha:** Abril 2026

### ¿Qué es?
Google anunció un conjunto de herramientas (`Android CLI` + `Android Skills` + `Android Knowledge Base`) que permiten a agentes de IA como **Claude Code** construir apps Android directamente desde la terminal, sin necesidad de Android Studio.

Resultados reportados: **70% menos tokens LLM** y tareas completadas **3x más rápido**.

### ¿Por qué nos sirve?
FreshCart ya tiene el backend preparado para app móvil (`capacitor://localhost` en CORS). Cuando queramos publicar en **Play Store**, este toolset permite:

- Crear y scaffoldear el APK con `android create` desde terminal
- Usar `Android Skills` para migrar el frontend React/Capacitor a app nativa
- Desplegar al dispositivo con `android run` sin tocar el IDE
- Claude Code puede hacer todo el proceso automáticamente

### Cuándo usarlo
Cuando se tome la decisión de **publicar FreshCart en Play Store** como app nativa. Por ahora el stack (Railway + Netlify + Capacitor) es suficiente.

---
