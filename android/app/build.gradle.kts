import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.openapi.generator)
    alias(libs.plugins.ksp)
}

// ---- API client generated from the server's OpenAPI spec (never committed) -------------------
val generatedApiDir = layout.buildDirectory.dir("generated/openapi")

openApiGenerate {
    generatorName.set("kotlin")
    inputSpec.set(rootProject.file("../frontend/openapi.json").absolutePath)
    outputDir.set(generatedApiDir.get().asFile.absolutePath)
    packageName.set("dev.pulse.api")
    library.set("jvm-retrofit2")
    typeMappings.set(mapOf("number" to "kotlin.Double"))
    configOptions.set(
        mapOf(
            "serializationLibrary" to "kotlinx_serialization",
            "useCoroutines" to "true",
            "dateLibrary" to "string",
            "omitGradleWrapper" to "true",
        ),
    )
    // Only the models: the app is standalone (Health Connect) and reuses the API's model
    // classes as its UI data types, so screens stay identical to the server-backed version.
    globalProperties.set(mapOf("models" to ""))
    generateApiTests.set(false)
    generateModelTests.set(false)
    generateApiDocumentation.set(false)
    generateModelDocumentation.set(false)
}

// openapi-generator's OpenAPI 3.1 support turns "array of (number | null)" into List<Double>.
// FastAPI emits those for e.g. steps_curve.today (null = hours that haven't happened yet).
// Read the spec and make exactly those element types nullable in the generated models.
// Runs as the last action of openApiGenerate, so the task's output is always the patched code.
tasks.named("openApiGenerate") {
    val spec = rootProject.file("../frontend/openapi.json")
    val modelsDir = generatedApiDir.map { it.dir("src/main/kotlin/dev/pulse/api/models") }
    val outDir = generatedApiDir
    // Start clean: the generator never deletes files it no longer produces.
    doFirst { outDir.get().asFile.deleteRecursively() }
    doLast {
        @Suppress("UNCHECKED_CAST")
        val root = groovy.json.JsonSlurper().parse(spec) as Map<String, Any?>
        val schemas = ((root["components"] as Map<String, Any?>)["schemas"] as Map<String, Any?>)

        fun nullableItems(items: Any?): Boolean {
            val m = items as? Map<*, *> ?: return false
            val any = m["anyOf"] as? List<*> ?: return false
            return any.any { (it as? Map<*, *>)?.get("type") == "null" }
        }

        fun camel(s: String) = s.split('_').mapIndexed { i, w -> if (i == 0) w else w.replaceFirstChar(Char::uppercase) }.joinToString("")
        var patched = 0
        for ((name, schema) in schemas) {
            val props = (schema as? Map<*, *>)?.get("properties") as? Map<*, *> ?: continue
            val file = modelsDir.get().file("$name.kt").asFile
            if (!file.exists()) continue
            var text = file.readText()
            for ((prop, def) in props) {
                val d = def as? Map<*, *> ?: continue
                if (d["type"] == "array" && nullableItems(d["items"])) {
                    val field = camel(prop as String)
                    val re = Regex("""(val `?$field`?: kotlin\.collections\.List<)([\w.]+)(>)""")
                    text = re.replace(text) { "${it.groupValues[1]}${it.groupValues[2]}?${it.groupValues[3]}" }
                    patched++
                }
            }
            file.writeText(text)
        }
        logger.info("patched $patched nullable array fields")
    }
}

// ---- Release signing from a local, git-ignored keystore (scripts/android-keystore.sh) ---------
val keystoreProps =
    Properties().apply {
        val f = rootProject.file("keystore.properties")
        if (f.exists()) f.inputStream().use { load(it) }
    }

android {
    namespace = "dev.pulse.app"
    compileSdk = 36

    defaultConfig {
        applicationId = "dev.pulse.app"
        minSdk = 29
        targetSdk = 36
        versionCode = 2
        versionName = "2.0.0"
    }

    signingConfigs {
        if (keystoreProps.isNotEmpty()) {
            create("release") {
                storeFile = rootProject.file(keystoreProps.getProperty("storeFile"))
                storePassword = keystoreProps.getProperty("storePassword")
                keyAlias = keystoreProps.getProperty("keyAlias")
                keyPassword = keystoreProps.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.findByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    sourceSets["main"].java.srcDir(generatedApiDir.map { it.dir("src/main/kotlin") })

    lint {
        abortOnError = true
        warningsAsErrors = false
        checkDependencies = false
        // Generated client code is not ours to lint.
        ignoreWarnings = false
        // ObsoleteSdkInt: adaptive icons must stay in mipmap-anydpi-v26 for AAPT.
        disable += setOf("GradleDependency", "NewerVersionAvailable", "AndroidGradlePluginVersion", "ObsoleteSdkInt")
    }

    testOptions {
        unitTests.isReturnDefaultValues = true
    }
}

kotlin {
    // Compile with the JDK running Gradle (Android Studio's bundled JDK 21), target Java 17.
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

tasks.named("preBuild") { dependsOn("openApiGenerate") }

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.graphics)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)
    debugImplementation(libs.compose.ui.tooling)
    implementation(libs.glance.appwidget)
    implementation(libs.glance.material3)
    implementation(libs.work.runtime)
    implementation(libs.datastore.preferences)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.android)

    implementation(libs.health.connect)
    implementation(libs.room.runtime)
    implementation(libs.room.ktx)
    ksp(libs.room.compiler)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
}
