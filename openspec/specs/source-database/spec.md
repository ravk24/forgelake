# source-database Specification

## Purpose
Defines the PostgreSQL databases that simulate ForgeLake's Production, Inventory and Maintenance operational systems. It sets their structure, which integrity rules they enforce, and the change-tracking columns that incremental extraction depends on.

## Requirements

### Requirement: One schema per operational system
The source database SHALL contain exactly three application schemas: `production` (factory, product, production_order, production_record), `inventory` (warehouse, inventory_transaction) and `maintenance` (machine, maintenance_record). Each master entity SHALL be stored only in the schema of its owning system.

#### Scenario: Schemas and tables present
- **WHEN** the source schemas are built on an empty database
- **THEN** the three schemas exist and contain exactly the eight listed tables

#### Scenario: No duplicated master data
- **WHEN** the inventory and maintenance schemas are inspected
- **THEN** neither contains a factory or product table; they refer to those entities by identifier only

### Requirement: Business identifiers as primary keys
Each table SHALL use a text business identifier as its primary key, in a fixed documented format per entity (for example `FAC-001` for factories, `MCH-0001` for machines). A schema SHALL reject a row whose own primary key is missing, duplicated or in the wrong format.

#### Scenario: Duplicate key rejected
- **WHEN** a row is inserted with a primary key that already exists in that table
- **THEN** the insert fails with a unique-violation error

#### Scenario: Malformed own key rejected
- **WHEN** a factory row is inserted with identifier `fac_1`
- **THEN** the insert fails with a check-violation error

### Requirement: Foreign keys enforced within a system
References between tables in the same schema SHALL be enforced by foreign-key constraints, so that a schema can't hold a child row whose parent doesn't exist in that schema.

#### Scenario: Orphan within a schema rejected
- **WHEN** a production record is inserted for an order identifier that does not exist in `production.production_order`
- **THEN** the insert fails with a foreign-key-violation error

### Requirement: References across systems not enforced
References to an entity owned by another schema (for example `inventory.warehouse.factory_id`, `inventory.inventory_transaction.product_id`, `maintenance.machine.factory_id`) SHALL NOT be enforced by the database. They SHALL accept missing, unknown or inconsistently formatted values, because independent operational systems can't validate each other's data.

#### Scenario: Unknown cross-system reference accepted
- **WHEN** an inventory transaction is inserted with a `product_id` that does not exist in `production.product`
- **THEN** the insert succeeds

#### Scenario: Inconsistent or missing cross-system reference accepted
- **WHEN** a machine is inserted with `factory_id` `fac_1`, or an inventory transaction with a null `product_id`
- **THEN** the insert succeeds

### Requirement: Business-rule quantities not enforced
Inventory transaction quantities SHALL NOT be range-checked by the database, so that invalid quantities, such as negative units, can exist in the source as they would in a weakly validated system. Every rule the database leaves unenforced SHALL be listed in the data-model documentation as a check the lakehouse is responsible for.

#### Scenario: Negative quantity accepted at source
- **WHEN** an inventory transaction is inserted with quantity -50
- **THEN** the insert succeeds

#### Scenario: Unenforced rules documented
- **WHEN** the data-model documentation is read
- **THEN** it lists every unenforced cross-system reference and business rule, together with the layer that must check it

### Requirement: Allowed values enforced for status and type columns
Status and type columns SHALL accept only their documented values (for example production order status `planned`, `released`, `in_progress`, `completed`, `cancelled`).

#### Scenario: Undocumented status rejected
- **WHEN** a production order is inserted with status `done`
- **THEN** the insert fails with a check-violation error

### Requirement: Change-tracking columns on every table
Every source table SHALL have `created_at` and `updated_at` timestamps with time zone and an `is_deleted` boolean, all non-null. A new row SHALL default to the current time for both timestamps and to `is_deleted = false`.

#### Scenario: Defaults on insert
- **WHEN** a row is inserted without values for the change-tracking columns
- **THEN** `created_at` and `updated_at` are set to the insertion time and `is_deleted` is false

### Requirement: updated_at advances on update
An update that does not set `updated_at` explicitly SHALL set it to the current time. An update that sets `updated_at` explicitly SHALL keep the supplied value, so that late-arriving changes can be simulated.

#### Scenario: Automatic advance
- **WHEN** a row is updated without changing `updated_at`
- **THEN** its `updated_at` becomes later than its previous value

#### Scenario: Explicit value kept
- **WHEN** a row is updated with `updated_at` set to a time in the past
- **THEN** the stored `updated_at` equals the supplied past time

### Requirement: Soft deletes only
Source rows SHALL be deleted by setting `is_deleted = true`, which also advances `updated_at`. The database SHALL reject row deletion on every source table, because watermark extraction can't detect a removed row.

#### Scenario: Soft delete visible to watermark
- **WHEN** a row is soft-deleted
- **THEN** the row still exists with `is_deleted = true` and an `updated_at` later than before the delete

#### Scenario: Hard delete rejected
- **WHEN** a `DELETE` statement targets a row in any source table
- **THEN** the statement fails with an error explaining that rows must be soft-deleted, and the row remains

### Requirement: Watermark-friendly access path
Every source table SHALL have an index whose leading column is `updated_at`, so that incremental extraction by `updated_at` doesn't need a full table scan.

#### Scenario: Index present
- **WHEN** the indexes of each source table are listed
- **THEN** each table has an index whose leading column is `updated_at`

### Requirement: Reproducible schema build
The schemas SHALL be built from versioned DDL files in the repository by a single documented command. The command SHALL refuse to drop existing schemas unless a reset is explicitly requested.

#### Scenario: Build on empty database
- **WHEN** the build command runs against a database without the source schemas
- **THEN** all schemas, tables, constraints, triggers and indexes are created and the command exits with status 0

#### Scenario: Existing schemas protected
- **WHEN** the build command runs against a database that already has the source schemas, without the reset option
- **THEN** it changes nothing, explains that a reset is required, and exits with a non-zero status

#### Scenario: Explicit reset
- **WHEN** the build command runs with the reset option
- **THEN** the source schemas are dropped and rebuilt from the DDL files

### Requirement: Connection settings outside the code
Database connection settings (host, port, database, user) SHALL have documented defaults that environment variables can override. The password SHALL never be stored in the repository and SHALL come from the user's local credential configuration.

#### Scenario: Override by environment
- **WHEN** the database-name environment variable is set
- **THEN** connections use that database instead of the default

#### Scenario: No secret in repository
- **WHEN** the repository's tracked files are searched for the database password
- **THEN** it is not found

### Requirement: Least-privilege access
The pipeline SHALL connect as a dedicated non-superuser role that owns the source databases. A separate test database SHALL exist, so that automated tests never modify the development source database.

#### Scenario: Non-superuser role
- **WHEN** the connected role's attributes are queried
- **THEN** it is not a superuser

#### Scenario: Tests isolated from development data
- **WHEN** the database integration tests run
- **THEN** they build and modify only the test database
