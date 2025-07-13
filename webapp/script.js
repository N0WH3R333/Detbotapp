document.addEventListener('DOMContentLoaded', () => {
    const tg = window.Telegram.WebApp;
    tg.ready();
    tg.expand();

    const catalogContainer = document.getElementById('catalog-container');
    const searchInput = document.getElementById('search-input');
    const searchResultsContainer = document.getElementById('search-results-container');
    const modal = document.getElementById('gallery-modal');
    const modalImage = document.getElementById('gallery-image');
    const modalCounter = document.getElementById('gallery-counter');
    const closeModalBtn = document.querySelector('.close-btn');
    const prevBtn = document.querySelector('.prev-btn');
    const nextBtn = document.querySelector('.next-btn');
    let allCategoriesData = []; // Хранилище всех данных каталога

    let allProducts = {}; // Хранилище всех товаров по ID для быстрого доступа
    let currentGalleryImages = [];
    let currentImageIndex = 0;
    let cart = {}; // Наша корзина { productId: quantity }

    // --- 1. Загрузка товаров с сервера ---
    async function fetchProducts() {
        // Используем относительный путь. Запрос пойдет на тот же домен, с которого загружена страница.
        const apiUrl = '/api/products'; 
        
        // Лог для отладки, чтобы видеть, куда идет запрос
        console.log(`Fetching products from: ${apiUrl}`);

        // Показываем индикатор загрузки
        catalogContainer.innerHTML = '<div class="loader"></div>';

        try {
            const response = await fetch(apiUrl);
            if (!response.ok) {
                throw new Error(`Ошибка сети: ${response.status}`);
            }
            allCategoriesData = await response.json();
            // Сохраняем все товары в allProducts для быстрого доступа (для корзины и поиска)
            allCategoriesData?.forEach(cat => {
                cat?.subcategories?.forEach(subcat => {
                    subcat?.products?.forEach(prod => {
                        allProducts[prod.id] = prod;
                    });
                });
            });
            renderCategoryMenu(); // Рендерим меню категорий вместо всего каталога
        } catch (error) {
            catalogContainer.innerHTML = `<div class="error-message">Не удалось загрузить товары. Попробуйте позже.</div>`;
            console.error("Ошибка при загрузке товаров:", error);
        }
    }

    // --- 2. Отрисовка меню категорий ---
    function renderCategoryMenu() {
        catalogContainer.innerHTML = '';
        const menuTitle = document.createElement('h2');
        menuTitle.className = 'category-title';
        menuTitle.textContent = 'Разделы магазина';
        catalogContainer.appendChild(menuTitle);

        const menuGrid = document.createElement('div');
        menuGrid.className = 'category-menu-grid';

        if (allCategoriesData.length === 0) {
            const noItems = document.createElement('p');
            noItems.textContent = 'Разделы не найдены.';
            menuGrid.appendChild(noItems);
        } else {
            allCategoriesData.forEach(category => {
                const categoryButton = document.createElement('button');
                categoryButton.className = 'category-menu-button';
                categoryButton.textContent = category.name;
                categoryButton.addEventListener('click', () => renderProductsForCategory(category.name));
                menuGrid.appendChild(categoryButton);
            });
        }
        catalogContainer.appendChild(menuGrid);
    }

    // --- 3. Отрисовка товаров для выбранной категории ---
    function renderProductsForCategory(categoryName) {
        catalogContainer.innerHTML = '';
        const selectedCategory = allCategoriesData.find(cat => cat.name === categoryName);

        if (!selectedCategory) {
            renderCategoryMenu(); // Если категория не найдена, вернуться в меню
            return;
        }

        // Кнопка "Назад"
        const backButton = document.createElement('button');
        backButton.className = 'back-to-menu-btn';
        backButton.innerHTML = '&larr; Назад к разделам';
        backButton.addEventListener('click', renderCategoryMenu);
        catalogContainer.appendChild(backButton);

        const categoryElement = document.createElement('div');
        categoryElement.className = 'category';

        const categoryTitle = document.createElement('h2');
        categoryTitle.className = 'category-title';
        categoryTitle.textContent = selectedCategory.name;
        categoryElement.appendChild(categoryTitle);

        if (selectedCategory.subcategories.length === 0 || selectedCategory.subcategories.every(s => s.products.length === 0)) {
            const noProducts = document.createElement('p');
            noProducts.className = 'info-message';
            noProducts.textContent = 'В этом разделе пока нет товаров.';
            categoryElement.appendChild(noProducts);
        } else {
            selectedCategory.subcategories.forEach(subcategory => {
                if (subcategory.products.length === 0) return; // Не отображаем пустые подкатегории

                const subcategoryTitle = document.createElement('h3');
                subcategoryTitle.className = 'subcategory-title';
                subcategoryTitle.textContent = subcategory.name;
                categoryElement.appendChild(subcategoryTitle);

                const productsGrid = document.createElement('div');
                productsGrid.className = 'products-grid';

                subcategory.products.forEach(product => {
                    const productCard = createProductCard(product);
                    productsGrid.appendChild(productCard);
                });
                categoryElement.appendChild(productsGrid);
            });
        }

        catalogContainer.appendChild(categoryElement);
    }

    // --- 4. Создание карточки товара ---
    function createProductCard(product) {
        const card = document.createElement('div');
        card.className = 'product-card';

        const imageContainer = document.createElement('div');
        imageContainer.className = 'product-image-container';
        // Убедимся, что товар есть в allProducts перед открытием галереи
        if (allProducts[product.id]) {
            imageContainer.addEventListener('click', () => openGallery(product.id));
        }
        
        const image = document.createElement('img');
        image.className = 'product-image';
        image.src = product.imageUrl || 'placeholder.png'; // Используем imageUrl, который отдает бот
        image.alt = product.name;
        image.onerror = () => { image.src = 'placeholder.png'; }; // Заглушка, если фото не загрузилось
        
        imageContainer.appendChild(image);

        const info = document.createElement('div');
        info.className = 'product-info';

        const name = document.createElement('p');
        name.className = 'product-name';
        name.textContent = product.name;

        const price = document.createElement('p');
        price.className = 'product-price';
        price.textContent = `${product.price} руб.`;

        const addButton = document.createElement('button');
        addButton.className = 'add-to-cart-btn';
        addButton.textContent = 'В корзину';
        addButton.addEventListener('click', (e) => { e.stopPropagation(); addToCart(product.id); });

        info.appendChild(name);
        info.appendChild(price);
        info.appendChild(addButton);
        
        card.appendChild(imageContainer);
        card.appendChild(info);

        return card;
    }

    // --- 5. Логика галереи ---
    function openGallery(productId) {
        const product = allProducts[productId];
        if (!product) return;

        // Собираем все фото: главное + детальные
        currentGalleryImages = [product.imageUrl, ...(product.detailImages || [])].filter(Boolean);
        if (currentGalleryImages.length === 0) return;

        currentImageIndex = 0;
        updateGalleryView();
        modal.style.display = 'flex';
    }

    function closeGallery() { modal.style.display = 'none'; }

    function updateGalleryView() {
        modalImage.src = currentGalleryImages[currentImageIndex];
        modalCounter.textContent = `${currentImageIndex + 1} / ${currentGalleryImages.length}`;
        prevBtn.style.display = currentGalleryImages.length > 1 ? 'block' : 'none';
        nextBtn.style.display = currentGalleryImages.length > 1 ? 'block' : 'none';
    }

    function showNextImage() { currentImageIndex = (currentImageIndex + 1) % currentGalleryImages.length; updateGalleryView(); }
    function showPrevImage() { currentImageIndex = (currentImageIndex - 1 + currentGalleryImages.length) % currentGalleryImages.length; updateGalleryView(); }

    // --- 6. Логика корзины ---
    function addToCart(productId) {
        if (cart[productId]) {
            cart[productId]++;
        } else {
            cart[productId] = 1;
        }
        tg.HapticFeedback.impactOccurred('light');
        updateMainButton();
    }

    function calculateTotalPrice() {
        let total = 0;
        for (const productId in cart) {
            total += allProducts[productId].price * cart[productId];
        }
        return total;
    }

    function updateMainButton() {
        const totalPrice = calculateTotalPrice();
        if (totalPrice > 0) {
            tg.MainButton.setText(`Оформить заказ на ${totalPrice} руб.`);
            tg.MainButton.show();
        } else {
            tg.MainButton.hide();
        }
    }

    // Обработчик нажатия на главную кнопку
    tg.onEvent('mainButtonClicked', () => {
        const dataToSend = {
            action: 'checkout',
            cart: cart
        };
        tg.sendData(JSON.stringify(dataToSend));
    });

    // --- 7. Логика поиска ---
    function performSearch(query) {
        query = query.toLowerCase().trim();

        if (!query) {
            // Если запрос пустой, показываем основной каталог и прячем результаты поиска
            searchResultsContainer.style.display = 'none';
            catalogContainer.style.display = 'block';
            return;
        }

        // Показываем результаты поиска и прячем основной каталог
        catalogContainer.style.display = 'none';
        searchResultsContainer.style.display = 'block';
        searchResultsContainer.innerHTML = ''; // Очищаем предыдущие результаты

        const results = Object.values(allProducts).filter(product => {
            const nameMatch = product.name.toLowerCase().includes(query);
            const descriptionMatch = product.description ? product.description.toLowerCase().includes(query) : false;
            return nameMatch || descriptionMatch;
        });

        const resultsTitle = document.createElement('h2');
        resultsTitle.className = 'category-title';
        resultsTitle.textContent = `Результаты поиска: "${query}"`;
        searchResultsContainer.appendChild(resultsTitle);

        if (results.length === 0) {
            const noResults = document.createElement('p');
            noResults.className = 'info-message';
            noResults.textContent = 'Ничего не найдено.';
            searchResultsContainer.appendChild(noResults);
        } else {
            const productsGrid = document.createElement('div');
            productsGrid.className = 'products-grid';
            results.forEach(product => {
                const productCard = createProductCard(product);
                productsGrid.appendChild(productCard);
            });
            searchResultsContainer.appendChild(productsGrid);
        }
    }

    // --- Навешиваем обработчики событий ---
    closeModalBtn.addEventListener('click', closeGallery);
    nextBtn.addEventListener('click', showNextImage);
    prevBtn.addEventListener('click', showPrevImage);
    searchInput.addEventListener('input', (e) => performSearch(e.target.value));

    // --- Запускаем загрузку ---
    fetchProducts();
});
