-- Soporte de resultados SIBOKIT. Script idempotente para SQL Server.
DECLARE @schema sysname = N'dbo';
DECLARE @tabla nvarchar(300) = QUOTENAME(@schema) + N'.' + QUOTENAME(N'sibokits_resultados');
DECLARE @sql nvarchar(max);

IF SCHEMA_ID(@schema) IS NULL
BEGIN
    SET @sql = N'CREATE SCHEMA ' + QUOTENAME(@schema);
    EXEC sp_executesql @sql;
END;

IF OBJECT_ID(QUOTENAME(@schema) + N'.' + QUOTENAME(N'muestras'), N'U') IS NULL
    THROW 50000, 'No existe la tabla de muestras. Crear la tabla base antes de aplicar esta migracion.', 1;

IF OBJECT_ID(@tabla, N'U') IS NULL
BEGIN
    SET @sql = N'CREATE TABLE ' + @tabla + N' (
        -- Debe coincidir exactamente con muestras.protocolo para crear la FK.
        protocolo nvarchar(255) NOT NULL,
        codigo_sibokit varchar(255) NOT NULL,
        h2 nvarchar(max) NOT NULL,
        ch4 nvarchar(max) NOT NULL,
        co2 nvarchar(max) NOT NULL,
        factor_correccion nvarchar(max) NOT NULL,
        valores_descartados nvarchar(max) NOT NULL CONSTRAINT DF_sibokit_descartados DEFAULT (''[]''),
        valoracion varchar(10) NOT NULL,
        descripcion nvarchar(max) NOT NULL,
        nota_adicional nvarchar(max) NULL,
        cargado_en varchar(20) NOT NULL,
        usuario_id varchar(255) NULL,
        created_at datetime NOT NULL CONSTRAINT DF_sibokit_created DEFAULT (GETDATE()),
        updated_at datetime NOT NULL CONSTRAINT DF_sibokit_updated DEFAULT (GETDATE()),
        CONSTRAINT PK_sibokits_resultados PRIMARY KEY (protocolo),
        CONSTRAINT FK_sibokits_resultados_muestras FOREIGN KEY (protocolo)
            REFERENCES ' + QUOTENAME(@schema) + N'.muestras(protocolo)
    )';
    EXEC sp_executesql @sql;
END;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_sibokits_codigo' AND object_id = OBJECT_ID(@tabla))
BEGIN
    SET @sql = N'CREATE UNIQUE INDEX IX_sibokits_codigo ON ' + @tabla + N'(codigo_sibokit)';
    EXEC sp_executesql @sql;
END;
