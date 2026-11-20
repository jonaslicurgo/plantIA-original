package com.plantia.ui

import androidx.compose.ui.res.stringResource
import com.plantia.R
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Book
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.plantia.api.PlantIAClient
import com.plantia.data.ThemeMode
import com.plantia.ui.screens.AboutScreen
import com.plantia.ui.screens.BotanicalProfileScreen
import com.plantia.ui.screens.CameraScreen
import com.plantia.ui.screens.EncyclopediaScreen
import com.plantia.ui.screens.DetailScreen
import com.plantia.ui.screens.PlantsScreen
import com.plantia.ui.screens.PlantHealthScreen
import com.plantia.ui.screens.SettingsScreen

sealed class Screen(val route: String, val label: Int) {
    data object Plants : Screen("plants", R.string.planet_plants)
    data object Camera : Screen("camera", R.string.planet_identify)
    data object Health : Screen("health/{id}", R.string.health_title) {
        fun route(id: Int) = "health/$id"
    }
    data object Encyclopedia : Screen("encyclopedia", R.string.botany_title)
    data object BotanicalProfile : Screen("botanical/{id}", R.string.botany_open) {
        fun route(id: Int) = "botanical/$id"
    }
    data object Settings : Screen("settings", R.string.planet_settings)
    data object About : Screen("about", R.string.planet_about)
    data object Detail : Screen("detail/{id}", R.string.planet_detail) {
        fun route(id: Int) = "detail/$id"
    }
}

private fun shouldShowBottomBar(route: String?): Boolean {
    if (route == null) return true
    if (route.startsWith("detail/")) return false
    if (route.startsWith("camera/refine/")) return false
    if (route == Screen.About.route) return false
    return route in listOf(Screen.Plants.route, Screen.Camera.route, Screen.Encyclopedia.route, Screen.Settings.route)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PlantIAApp(
    navController: NavHostController = rememberNavController(),
    initialPlantId: Int? = null,
    themeMode: ThemeMode = ThemeMode.SYSTEM,
    onThemeModeChange: (ThemeMode) -> Unit = {},
) {
    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = backStackEntry?.destination?.route
    val showBottomBar = shouldShowBottomBar(currentRoute)

    LaunchedEffect(initialPlantId) {
        if (initialPlantId != null) {
            navController.navigate(Screen.Detail.route(initialPlantId)) {
                launchSingleTop = true
            }
        }
    }

    Scaffold(
        bottomBar = {
            if (showBottomBar) {
                NavigationBar {
                    val items = listOf(Screen.Plants, Screen.Camera, Screen.Encyclopedia, Screen.Settings)
                    items.forEach { screen ->
                        val selected = currentRoute == screen.route
                        NavigationBarItem(
                            selected = selected,
                            alwaysShowLabel = false,
                            onClick = {
                                navController.navigate(screen.route) {
                                    popUpTo(navController.graph.findStartDestination().id) {
                                        saveState = true
                                    }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            },
                            icon = {
                                when (screen) {
                                    Screen.Plants -> Icon(Icons.Default.Home, contentDescription = stringResource(screen.label))
                                    Screen.Camera -> Icon(Icons.Default.CameraAlt, contentDescription = stringResource(screen.label))
                                    Screen.Settings -> Icon(Icons.Default.Settings, contentDescription = stringResource(screen.label))
                                    Screen.Encyclopedia -> Icon(Icons.Default.Book, contentDescription = stringResource(screen.label))
                                    else -> {}
                                }
                            },
                            label = { Text(stringResource(screen.label)) },
                        )
                    }
                }
            }
        },
    ) { padding ->
        NavHost(
            navController = navController,
            startDestination = Screen.Plants.route,
            modifier = Modifier.padding(padding),
        ) {
            composable(Screen.Plants.route) {
                PlantsScreen(
                    onOpenCamera = { navController.navigate(Screen.Camera.route) },
                    onOpenDetail = { id -> navController.navigate(Screen.Detail.route(id)) },
                )
            }
            composable(Screen.Health.route, arguments = listOf(navArgument("id") { type = NavType.IntType })) { entry ->
                val id = entry.arguments?.getInt("id") ?: return@composable
                PlantHealthScreen(id, onOpenBotany = { navController.navigate(Screen.BotanicalProfile.route(id)) }) { navController.popBackStack() }
            }
            composable(Screen.Encyclopedia.route) {
                EncyclopediaScreen { id -> navController.navigate(Screen.BotanicalProfile.route(id)) }
            }
            composable(Screen.BotanicalProfile.route, arguments = listOf(navArgument("id") { type = NavType.IntType })) { entry ->
                val id = entry.arguments?.getInt("id") ?: return@composable
                BotanicalProfileScreen(id) { navController.popBackStack() }
            }
            composable(Screen.Camera.route) {
                CameraScreen(
                    onIdentified = { id ->
                        navController.navigate(Screen.Detail.route(id)) {
                            popUpTo(Screen.Plants.route)
                        }
                    },
                    onCancel = { navController.popBackStack() },
                )
            }
            composable(Screen.Settings.route) {
                SettingsScreen(
                    themeMode = themeMode,
                    onThemeModeChange = onThemeModeChange,
                    onOpenAbout = { navController.navigate(Screen.About.route) },
                )
            }
            composable(Screen.About.route) {
                AboutScreen(onBack = { navController.popBackStack() })
            }
            composable(Screen.Detail.route) { entry ->
                val id = entry.arguments?.getString("id")?.toIntOrNull() ?: return@composable
                DetailScreen(
                    plantaId = id,
                    onBack = { navController.popBackStack() },
                    onReIdentify = { navController.navigate("camera/refine/$id") },
                    onOpenHealth = { navController.navigate(Screen.Health.route(id)) },
                    onOpenBotany = { navController.navigate(Screen.BotanicalProfile.route(id)) },
                )
            }
            composable(
                route = "camera/refine/{id}",
                arguments = listOf(navArgument("id") { type = NavType.IntType }),
            ) { entry ->
                val id = entry.arguments?.getInt("id") ?: return@composable
                val context = LocalContext.current
                var refineName by remember { mutableStateOf<String?>(null) }
                LaunchedEffect(id) {
                    refineName = runCatching {
                        PlantIAClient.api(context).detalle(id).nombre_comun
                    }.getOrNull()
                }
                CameraScreen(
                    refinePlantName = refineName,
                    onIdentified = { newId ->
                        navController.navigate(Screen.Detail.route(newId)) {
                            popUpTo(Screen.Detail.route(id)) { inclusive = true }
                        }
                    },
                    onCancel = { navController.popBackStack() },
                )
            }
        }
    }
}
