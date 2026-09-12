# Cómo trabajamos

Este documento es igual en los tres repos (`sst-api`, `sst-web`, `sst-mobile`).

## Ramas

```
main                 ← solo código estable y entregable. Nunca se commitea directo.
└── develop          ← rama de integración. De aquí salen y aquí vuelven las features.
    ├── feature/authentication
    ├── feature/reports-offline-sync
    └── fix/iperc-risk-level
```

| Prefijo     | Para qué                                   | Sale de  | Vuelve a |
|-------------|--------------------------------------------|----------|----------|
| `feature/`  | nueva funcionalidad                        | develop  | develop  |
| `fix/`      | corrección de bug                          | develop  | develop  |
| `hotfix/`   | bug urgente que ya está en producción      | main     | main **y** develop |
| `docs/`     | solo documentación                         | develop  | develop  |
| `release/`  | preparar una entrega (versión, changelog)  | develop  | main **y** develop |

Nombres de rama en minúscula y con guiones: `feature/reports-offline-sync`, no `feature/ReportsOfflineSync`.

## Flujo de una feature

```bash
git checkout develop
git pull origin develop
git checkout -b feature/authentication

# ... trabajas, commiteando seguido ...
git add .
git commit -m "feat(auth): agregar endpoint de registro de usuario"

git push -u origin feature/authentication
# Abres el Pull Request en GitHub hacia develop
```

Cuando el PR está aprobado y el CI pasa:

```bash
# Desde GitHub: "Squash and merge" hacia develop
git checkout develop && git pull origin develop
git branch -d feature/authentication
```

## Conventional Commits

Formato: `tipo(alcance): descripción`

```
feat(auth): agregar login con JWT
fix(reports): evitar duplicados al sincronizar offline
docs(readme): documentar variables de entorno
refactor(iperc): extraer cálculo de nivel de riesgo a una property
test(reports): cubrir el cierre de hallazgos
chore(deps): actualizar drf-spectacular a 0.28
```

Reglas:

- tipo en minúscula, de la lista: `feat` `fix` `docs` `style` `refactor` `perf` `test` `build` `ci` `chore` `revert`
- descripción en minúscula, modo imperativo ("agregar", no "agregué" ni "agregado")
- máximo 100 caracteres en la primera línea
- un cambio que rompe el contrato del API lleva `!`: `feat(reports)!: renombrar campo status a state`

El hook `commit-msg` lo valida localmente y el workflow de Actions lo valida en cada PR. **Actívalo después de clonar:**

```bash
bash scripts/setup-hooks.sh
```

## Merges

- **feature → develop**: *Squash and merge*. Deja un historial limpio, un commit por feature.
- **develop → main**: *Merge commit* (`--no-ff`). Cada merge a main es una entrega y se etiqueta:
  ```bash
  git checkout main && git pull
  git merge --no-ff develop -m "chore(release): v0.2.0"
  git tag -a v0.2.0 -m "Sprint 2: reportes offline e IPERC"
  git push origin main --tags
  ```
- Nunca `git push --force` a `main` ni a `develop`.

## Pull Requests

- Apuntan a `develop` (salvo hotfix y release, que van a `main`)
- Título con el mismo formato que los commits: `feat(auth): login con JWT`
- Cierran su issue con `Closes #12` en la descripción
- El CI tiene que estar verde antes de mergear
- Si el PR cambia el contrato del API, se avisa en el PR para que web y móvil se enteren
