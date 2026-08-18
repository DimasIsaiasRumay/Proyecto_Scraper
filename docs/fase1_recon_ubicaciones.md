# Reporte de Reconocimiento en Odoo (Fase 1)

> Resultado de la exploración manual en modo solo lectura sobre Odoo 19.0.
> Generado por `scripts/manual_exploration/explorar_ubicaciones_odoo.py` el 18/08/2026.
> No contiene credenciales, URLs ni datos sensibles.

---

## 1. Empresas (`res.company`)

```json
[
  {
    "id": 1,
    "name": "SET IN SAS"
  }
]
```

## 2. XML ID del padre (`ir.model.data`)

### 2a. `location_production`
```json
[]
```

### 2b. `stock_location_production`
```json
[]
```

*Nota:* Los XML IDs consultados no devolvieron registros en `ir.model.data`. Se utiliza el fallback por nombre y atributos (`name='Production'`, `location_id=False`, `usage='production'`, `active=True`).

## 3. Padre por nombre y atributos (`stock.location`)

```json
[
  {
    "id": 12,
    "name": "Production",
    "complete_name": "Production",
    "usage": "production",
    "location_id": false,
    "company_id": [
      1,
      "SET IN SAS"
    ],
    "active": true
  }
]
```

## 4. Registros con `usage='production'`

```json
[
  {
    "id": 12,
    "name": "Production",
    "complete_name": "Production",
    "usage": "production",
    "location_id": false,
    "active": true
  },
  {
    "id": 16,
    "name": "OP-CTOM-GAB-120826-0002",
    "complete_name": "Production/OP-CTOM-GAB-120826-0002",
    "usage": "production",
    "location_id": [
      12,
      "Production"
    ],
    "active": true
  }
]
```

## 5. Hijos actuales del padre resuelto (`location_id=12`)

```json
[
  {
    "id": 16,
    "name": "OP-CTOM-GAB-120826-0002",
    "complete_name": "Production/OP-CTOM-GAB-120826-0002",
    "usage": "production",
    "active": true
  }
]
```

## 6. Inventario completo `stock.location` (activas e inactivas)

```json
[
  {
    "id": 2,
    "name": "Customers",
    "complete_name": "Customers",
    "usage": "customer",
    "location_id": false,
    "active": true
  },
  {
    "id": 3,
    "name": "Inter-company transit",
    "complete_name": "Inter-company transit",
    "usage": "transit",
    "location_id": false,
    "active": false
  },
  {
    "id": 11,
    "name": "Inventory adjustment",
    "complete_name": "Inventory adjustment",
    "usage": "inventory",
    "location_id": false,
    "active": true
  },
  {
    "id": 12,
    "name": "Production",
    "complete_name": "Production",
    "usage": "production",
    "location_id": false,
    "active": true
  },
  {
    "id": 16,
    "name": "OP-CTOM-GAB-120826-0002",
    "complete_name": "Production/OP-CTOM-GAB-120826-0002",
    "usage": "production",
    "location_id": [
      12,
      "Production"
    ],
    "active": true
  },
  {
    "id": 15,
    "name": "SET IN SAS",
    "complete_name": "SET IN SAS",
    "usage": "internal",
    "location_id": false,
    "active": true
  },
  {
    "id": 10,
    "name": "Traslado entre almacenes",
    "complete_name": "Traslado entre almacenes",
    "usage": "transit",
    "location_id": false,
    "active": false
  },
  {
    "id": 1,
    "name": "Vendors",
    "complete_name": "Vendors",
    "usage": "supplier",
    "location_id": false,
    "active": true
  },
  {
    "id": 4,
    "name": "WH",
    "complete_name": "WH",
    "usage": "view",
    "location_id": false,
    "active": true
  },
  {
    "id": 7,
    "name": "Control de calidad",
    "complete_name": "WH/Control de calidad",
    "usage": "internal",
    "location_id": [
      4,
      "WH"
    ],
    "active": false
  },
  {
    "id": 6,
    "name": "Entrada",
    "complete_name": "WH/Entrada",
    "usage": "internal",
    "location_id": [
      4,
      "WH"
    ],
    "active": false
  },
  {
    "id": 5,
    "name": "Existencias",
    "complete_name": "WH/Existencias",
    "usage": "internal",
    "location_id": [
      4,
      "WH"
    ],
    "active": true
  },
  {
    "id": 14,
    "name": "Posproducción",
    "complete_name": "WH/Posproducción",
    "usage": "internal",
    "location_id": [
      4,
      "WH"
    ],
    "active": false
  },
  {
    "id": 13,
    "name": "Preproducción",
    "complete_name": "WH/Preproducción",
    "usage": "internal",
    "location_id": [
      4,
      "WH"
    ],
    "active": false
  },
  {
    "id": 8,
    "name": "Salida",
    "complete_name": "WH/Salida",
    "usage": "internal",
    "location_id": [
      4,
      "WH"
    ],
    "active": false
  },
  {
    "id": 9,
    "name": "Zona de empaquetado",
    "complete_name": "WH/Zona de empaquetado",
    "usage": "internal",
    "location_id": [
      4,
      "WH"
    ],
    "active": false
  }
]
```

## 7. Choque de nombres (25 proyectos corrida 39)

```json
[
  {
    "id": 16,
    "name": "OP-CTOM-GAB-120826-0002",
    "complete_name": "Production/OP-CTOM-GAB-120826-0002",
    "location_id": [
      12,
      "Production"
    ],
    "usage": "production",
    "active": true
  }
]
```

## 8. Metadatos de campos (`fields_get` en `stock.location`)

```json
{
  "name": {
    "readonly": false,
    "required": true,
    "store": true,
    "type": "char"
  },
  "complete_name": {
    "readonly": true,
    "required": false,
    "store": true,
    "type": "char"
  },
  "active": {
    "readonly": false,
    "required": false,
    "store": true,
    "type": "boolean"
  },
  "usage": {
    "readonly": false,
    "required": true,
    "selection": [
      [
        "supplier",
        "Vendor"
      ],
      [
        "view",
        "Virtual"
      ],
      [
        "internal",
        "Internal"
      ],
      [
        "customer",
        "Customer"
      ],
      [
        "inventory",
        "Inventory Loss"
      ],
      [
        "production",
        "Production"
      ],
      [
        "transit",
        "Transit"
      ]
    ],
    "store": true,
    "type": "selection"
  },
  "location_id": {
    "readonly": false,
    "required": false,
    "store": true,
    "type": "many2one"
  },
  "company_id": {
    "readonly": false,
    "required": false,
    "store": true,
    "type": "many2one"
  }
}
```
