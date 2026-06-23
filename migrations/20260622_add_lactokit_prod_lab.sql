-- Crea lab.lactokits_resultados en PROD (schema lab).
-- Idempotente: no falla si ya existe. Requiere que lab.muestras exista.

DECLARE @schema sysname = N'lab';
DECLARE @muestras nvarchar(300) = QUOTENAME(@schema) + N'.' + QUOTENAME(N'muestras');
DECLARE @lactokits nvarchar(300) = QUOTENAME(@schema) + N'.' + QUOTENAME(N'lactokits_resultados');
DECLARE @sql nvarchar(max);

IF SCHEMA_ID(@schema) IS NULL
BEGIN
    SET @sql = N'CREATE SCHEMA ' + QUOTENAME(@schema);
    EXEC sp_executesql @sql;
END;

IF OBJECT_ID(@muestras, N'U') IS NULL
    THROW 50000, 'No existe lab.muestras. Crear la tabla base antes de aplicar esta migracion.', 1;

IF OBJECT_ID(@lactokits, N'U') IS NULL
BEGIN
    DECLARE @protocolo_tipo nvarchar(128);

    SELECT @protocolo_tipo =
        ty.name +
        CASE
            WHEN ty.name IN (N'varchar', N'char', N'varbinary', N'binary')
                THEN N'(' + CASE WHEN c.max_length = -1 THEN N'max' ELSE CONVERT(nvarchar(10), c.max_length) END + N')'
            WHEN ty.name IN (N'nvarchar', N'nchar')
                THEN N'(' + CASE WHEN c.max_length = -1 THEN N'max' ELSE CONVERT(nvarchar(10), c.max_length / 2) END + N')'
            WHEN ty.name IN (N'decimal', N'numeric')
                THEN N'(' + CONVERT(nvarchar(10), c.precision) + N',' + CONVERT(nvarchar(10), c.scale) + N')'
            WHEN ty.name IN (N'datetime2', N'time', N'datetimeoffset')
                THEN N'(' + CONVERT(nvarchar(10), c.scale) + N')'
            ELSE N''
        END +
        CASE WHEN c.collation_name IS NOT NULL THEN N' COLLATE ' + c.collation_name ELSE N'' END
    FROM sys.columns c
    JOIN sys.types ty ON c.user_type_id = ty.user_type_id
    WHERE c.object_id = OBJECT_ID(@muestras)
      AND c.name = N'protocolo';

    IF @protocolo_tipo IS NULL
        THROW 50001, 'No se pudo detectar el tipo de lab.muestras.protocolo.', 1;

    SET @sql = N'CREATE TABLE ' + @lactokits + N' (
        protocolo ' + @protocolo_tipo + N' NOT NULL,
        codigo_lactokit varchar(255) NOT NULL,
        h2 nvarchar(max) NOT NULL,
        ch4 nvarchar(max) NOT NULL,
        co2 nvarchar(max) NOT NULL,
        valoracion varchar(10) NOT NULL,
        descripcion varchar(255) NOT NULL,
        cargado_en varchar(16) NOT NULL,
        created_at datetime NOT NULL CONSTRAINT DF_lactokits_resultados_created_at DEFAULT (GETDATE()),
        updated_at datetime NOT NULL CONSTRAINT DF_lactokits_resultados_updated_at DEFAULT (GETDATE()),
        CONSTRAINT PK_lactokits_resultados PRIMARY KEY (protocolo),
        CONSTRAINT FK_lactokits_resultados_muestras
            FOREIGN KEY (protocolo)
            REFERENCES ' + @muestras + N'(protocolo)
    )';
    EXEC sp_executesql @sql;
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = N'IX_lactokits_resultados_codigo_lactokit'
      AND object_id = OBJECT_ID(@lactokits)
)
BEGIN
    SET @sql = N'CREATE UNIQUE INDEX IX_lactokits_resultados_codigo_lactokit
        ON ' + @lactokits + N'(codigo_lactokit)';
    EXEC sp_executesql @sql;
END;
