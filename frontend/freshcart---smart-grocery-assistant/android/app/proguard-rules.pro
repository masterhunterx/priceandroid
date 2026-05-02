# FreshCart ProGuard rules

# Capacitor WebView bridge — debe quedar intacto
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}

# Firebase Auth — evitar obfuscar clases de autenticación
-keep class com.google.firebase.** { *; }
-keep class com.google.android.gms.** { *; }

# Facebook SDK — no está incluido, ignorar referencias missing
-dontwarn com.facebook.**
-keep class com.facebook.** { *; }

# Capacitor Firebase Authentication plugin
-keep class io.capawesome.capacitorjs.plugins.firebase.** { *; }

# Mantener nombres de clases para stack traces legibles
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile
