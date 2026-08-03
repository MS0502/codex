plugins {
    id("com.android.application")
}

android {
    namespace = "io.github.ms0502.trdiag"
    compileSdk = 35

    defaultConfig {
        applicationId = "io.github.ms0502.trdiag"
        minSdk = 29
        targetSdk = 35
        versionCode = 18
        versionName = "18.0"
    }

    buildTypes {
        debug {
            isMinifyEnabled = false
        }
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
