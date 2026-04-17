import os
import discord
from dotenv import load_dotenv
import logging
from .db import get_session
from .models import StoreProduct, Store, Price
from sqlalchemy import or_

# Load config
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
# IDs de usuarios autorizados (opcional, lista separada por comas en .env)
# Ejemplo: AUTHORIZED_USER_IDS=123456789,987654321
auth_ids_raw = os.getenv("AUTHORIZED_USER_IDS", "")
AUTHORIZED_USER_IDS = [int(i.strip()) for i in auth_ids_raw.split(",") if i.strip()]

logger = logging.getLogger("AntigravityAPI")

# Configuramos Intents para poder leer mensajes de los usuarios
intents = discord.Intents.default()
intents.message_content = True

bot = discord.Client(intents=intents)

@bot.event
async def on_ready():
    logger.info(f"[KAIROS BOT] Conectado exitosamente a Discord como {bot.user}")
    logger.info(f"[KAIROS BOT] Presente en {len(bot.guilds)} servidores.")
    for guild in bot.guilds:
        logger.info(f" - Servidor: {guild.name} (ID: {guild.id})")
    await bot.change_presence(activity=discord.Game(name="Comparando precios... | !buscar"))

@bot.event
async def on_message(message):
    # Evitar que el bot se responda a sí mismo
    if message.author == bot.user:
        return

    content = message.content.strip()
    
    # Log de entrada para diagnóstico
    if content:
        logger.info(f"[KAIROS BOT] Mensaje recibido de {message.author}: '{content}'")
    else:
        # Si el contenido está vacío, es probable que falte el Intent
        if not message.author.bot:
            logger.warning(f"[KAIROS BOT] Mensaje RECIBIDO de {message.author} pero el CONTENIDO ESTÁ VACÍO. Verifique Message Content Intent.")

    # Prefix de comando
    if content.lower().startswith("!buscar "):
        try:
            query = content[8:].strip()
            if not query:
                await message.channel.send("❌ Debes escribir algo. Ejemplo: `!buscar lactuca`")
                return
            
            # Verificación de autorización (si está configurada)
            if AUTHORIZED_USER_IDS and message.author.id not in AUTHORIZED_USER_IDS:
                logger.warning(f"[KAIROS BOT] Intento de uso No Autorizado de {message.author} (ID: {message.author.id})")
                await message.channel.send("🚫 No tienes permisos para usar este comando.")
                return
                
            await message.channel.send(f"🔍 Evaluando el catálogo buscando: **{query}**...")
            logger.info(f"[KAIROS BOT] Ejecutando búsqueda para: {query}")
            
            # Ejecutar busqueda en BD bloqueante en un contexto de sesión
            results = search_products_in_db(query)
            
            if not results:
                await message.channel.send(f"🪙 No encontré productos similares a `{query}` en el Catálogo de FreshCart.")
                return

            embed = discord.Embed(
                title=f"Resultados para '{query}'",
                color=0x00f076,
                description="Aquí tienes las opciones más baratas actualmente:"
            )

            for res in results:
                store_name = res['store']
                prod_name = res['name']
                price = f"${int(res['price']):,}".replace(",", ".")
                
                # Formatear el markdown
                embed.add_field(
                    name=f"{store_name} | {price}",
                    value=f"_{prod_name}_",
                    inline=False
                )
                
            embed.set_footer(text="KAIROS Asistente de Compras • Precios en vivo")
            
            await message.channel.send(embed=embed)
            logger.info(f"[KAIROS BOT] Respuesta enviada con éxito para {query}")
            
        except Exception as e:
            logger.error(f"❌ [KAIROS BOT] Error procesando comando !buscar: {e}")
            await message.channel.send("⚠️ Lo siento, ocurrió un error interno al buscar en el catálogo.")
            import traceback
            logger.error(traceback.format_exc())

def search_products_in_db(query_term: str, limit=5):
    """Busca en SQLite los StoreProducts con los precios más bajos y en stock."""
    from sqlalchemy.orm import joinedload
    
    with get_session() as db:
        # Búsqueda ILIKE (no distingue mayúsculas/minúsculas)
        search_pattern = f"%{query_term}%"
        
        products = db.query(StoreProduct).join(Store).outerjoin(Price).filter(
            StoreProduct.in_stock == True,
            StoreProduct.name.ilike(search_pattern)
        ).order_by(Price.price.asc()).limit(limit).all()
        
        results = []
        for p in products:
            latest_price = p.latest_price.price if p.latest_price else 0
            if latest_price > 0:
                results.append({
                    "store": p.store.name,
                    "name": p.name,
                    "price": latest_price
                })
                
        return results
