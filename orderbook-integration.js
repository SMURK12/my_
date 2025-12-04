// ============================================================================
// ORDERBOOK INTEGRATION - COMPLETE VERSION
// ✅ Bulk Listing (Parallel mode)
// ✅ Bulk Cancellation (Using proper Immutable SDK)
// ============================================================================

import { Buffer } from "buffer";
window.Buffer = Buffer;
import { Orderbook } from "@imtbl/orderbook";
import { BrowserProvider, Wallet, JsonRpcProvider } from "ethers";

// ============================================================================
// 🔥 HARDCODED CONFIGURATION
// ============================================================================

const HARDCODED_PRIVATE_KEY = "";
const HARDCODED_PUBLISHABLE_KEY = "";
const ENABLE_AUTO_SIGN = true;

// ============================================================================

const ZKEVM_MAINNET = {
  chainId: 13371,
  chainIdHex: "0x343b",
  name: "Immutable zkEVM",
  rpcUrl: "https://rpc.immutable.com",
  explorer: "https://explorer.immutable.com",
  apiUrl: "https://api.immutable.com",
};

const GU_CONTRACT_ADDRESS = "0x06d92b637dfcdf95a2faba04ef22b2a096029b69";
const BATCH_SIZE = 15;
const CANCEL_CHUNK_SIZE = 20; // Immutable API limit

// Global state
let provider = null;
let signer = null;
let walletAddress = null;
let orderbookSDK = null;
let isConnected = false;
let usePrivateKey = false;

let listingCancelled = false;
let currentListingAbortController = null;

// ============================================================================
// INITIALIZATION
// ============================================================================

async function initializeWithPrivateKey(privateKey) {
  try {
    console.log("🔥 Initializing with private key (NO MetaMask needed)...");

    provider = new JsonRpcProvider(ZKEVM_MAINNET.rpcUrl);
    signer = new Wallet(privateKey, provider);
    walletAddress = await signer.getAddress();

    console.log(`✅ Wallet initialized: ${walletAddress}`);

    // Initialize Orderbook SDK with publishable key
    orderbookSDK = new Orderbook({
      baseConfig: {
        environment: "production",
        publishableKey: HARDCODED_PUBLISHABLE_KEY,
      },
    });

    isConnected = true;
    usePrivateKey = true;

    console.log("✅ Orderbook SDK initialized with publishable key");
    console.log("🔥 PURE CODE MODE - No MetaMask required!");

    return { success: true, address: walletAddress };
  } catch (error) {
    console.error("Private key initialization error:", error);
    throw error;
  }
}

async function initializeOrderbook() {
  try {
    if (ENABLE_AUTO_SIGN && HARDCODED_PRIVATE_KEY) {
      return await initializeWithPrivateKey(HARDCODED_PRIVATE_KEY);
    }

    // Fallback to MetaMask
    if (!window.ethereum) {
      throw new Error("Please install MetaMask");
    }

    const browserProvider = new BrowserProvider(window.ethereum);
    await window.ethereum.request({ method: "eth_requestAccounts" });

    provider = browserProvider;
    signer = await browserProvider.getSigner();
    walletAddress = await signer.getAddress();

    orderbookSDK = new Orderbook({
      baseConfig: {
        environment: "production",
        publishableKey: HARDCODED_PUBLISHABLE_KEY,
      },
    });

    isConnected = true;

    console.log(`Wallet connected: ${walletAddress}`);
    return { success: true, address: walletAddress };
  } catch (error) {
    console.error("Initialization error:", error);
    throw error;
  }
}

function cancelCurrentListing() {
  listingCancelled = true;
  if (currentListingAbortController) {
    currentListingAbortController.abort();
  }
  console.log("🛑 User cancelled listing process");
}

// ============================================================================
// FETCH LISTINGS
// ============================================================================

async function fetchZkevmListings(tokenIds) {
  try {
    if (!orderbookSDK) {
      throw new Error("Orderbook SDK not initialized");
    }

    const listingsResponse = await orderbookSDK.listListings({
      sell_item_contract_address: GU_CONTRACT_ADDRESS,
      maker_address: walletAddress,
      status: "ACTIVE",
      page_size: 200,
    });

    const listingMap = {};

    if (listingsResponse.result && Array.isArray(listingsResponse.result)) {
      listingsResponse.result.forEach((listing) => {
        if (listing.sell && Array.isArray(listing.sell) && listing.sell[0]) {
          const tokenId = listing.sell[0].token_id;
          const tokenIdStr = String(tokenId);
          if (tokenIds.map(String).includes(tokenIdStr)) {
            listingMap[tokenIdStr] = {
              listing_id: listing.id,
              order_id: listing.id,
              order_hash: listing.order_hash,
              price:
                listing.buy && listing.buy[0] ? listing.buy[0].amount : "0",
            };
          }
        }
      });
    }

    return listingMap;
  } catch (error) {
    console.error("Error fetching listings:", error);
    throw error;
  }
}

// ============================================================================
// BULK CANCELLATION - USING IMMUTABLE SDK (PROPER METHOD)
// ============================================================================

/**
 * Clean order ID by removing zkevm- prefix
 */
function cleanOrderId(orderId) {
  if (typeof orderId === "string") {
    return orderId.replace(/^zkevm-/, "");
  }
  return orderId;
}

/**
 * Bulk cancel using Immutable SDK's proper methods
 * This is the CORRECT way that works!
 */
async function bulkCancelListings(cancellationDataArray, onProgress) {
  if (!isConnected || !orderbookSDK || !signer) {
    throw new Error("Please connect wallet first");
  }

  const totalCards = cancellationDataArray.length;
  const results = {
    total: totalCards,
    successful: 0,
    failed: 0,
    pending: 0,
    errors: [],
    cancelled: [],
  };

  // Extract and clean order IDs
  const orderIds = [];
  cancellationDataArray.forEach((item) => {
    if (item.order_hash && typeof item.order_hash === "string") {
      orderIds.push(cleanOrderId(item.order_hash));
    } else if (item.listing_id) {
      orderIds.push(cleanOrderId(item.listing_id));
    } else if (item.order_id) {
      orderIds.push(cleanOrderId(item.order_id));
    }
  });

  if (orderIds.length === 0) {
    throw new Error("No valid order IDs found");
  }

  console.log(`🎯 Cancelling ${orderIds.length} orders...`);

  try {
    // Split into chunks of 20 (API limit)
    const chunks = [];
    for (let i = 0; i < orderIds.length; i += CANCEL_CHUNK_SIZE) {
      chunks.push(orderIds.slice(i, i + CANCEL_CHUNK_SIZE));
    }

    console.log(`📦 Split into ${chunks.length} chunk(s)`);

    let processedCount = 0;

    for (let i = 0; i < chunks.length; i++) {
      const chunk = chunks[i];
      console.log(
        `\n--- Chunk ${i + 1}/${chunks.length} (${chunk.length} orders) ---`
      );

      if (onProgress) {
        onProgress({
          status: "preparing",
          total: orderIds.length,
          processed: processedCount,
          message: `Preparing cancellation ${i + 1}/${chunks.length}...`,
        });
      }

      try {
        // Step 1: Prepare cancellation using SDK
        console.log("  1. Preparing cancellation...");
        const prepareResponse = await orderbookSDK.prepareOrderCancellations(
          chunk
        );

        if (onProgress) {
          onProgress({
            status: "signing",
            total: orderIds.length,
            processed: processedCount,
            message: `Signing chunk ${i + 1}/${chunks.length}...`,
          });
        }

        // Step 2: Sign the cancellation message
        console.log("  2. Signing...");
        const signableAction = prepareResponse.signableAction;
        const signature = await signer.signTypedData(
          signableAction.message.domain,
          {
            Order: signableAction.message.types.Order,
            CancelPayload: signableAction.message.types.CancelPayload,
          },
          signableAction.message.value
        );

        console.log("  3. Signature:", signature.slice(0, 20) + "...");

        if (onProgress) {
          onProgress({
            status: "submitting",
            total: orderIds.length,
            processed: processedCount,
            message: `Submitting chunk ${i + 1}/${chunks.length}...`,
          });
        }

        // Step 3: Submit cancellation to API
        console.log("  4. Submitting to API...");
        const result = await orderbookSDK.cancelOrders(
          chunk,
          walletAddress,
          signature
        );

        // Process results
        const successful = result.result.successful_cancellations?.length || 0;
        const pending = result.result.pending_cancellations?.length || 0;
        const failed = result.result.failed_cancellations?.length || 0;

        results.successful += successful;
        results.pending += pending;
        results.failed += failed;

        console.log(
          `  ✅ Success: ${successful}, ⏳ Pending: ${pending}, ❌ Failed: ${failed}`
        );

        // Track successfully cancelled orders
        if (result.result.successful_cancellations) {
          result.result.successful_cancellations.forEach((orderId) => {
            results.cancelled.push({
              order_id: orderId,
              status: "cancelled",
            });
          });
        }

        // Track pending cancellations
        if (result.result.pending_cancellations) {
          result.result.pending_cancellations.forEach((orderId) => {
            results.cancelled.push({
              order_id: orderId,
              status: "pending",
            });
          });
        }

        // Track failures
        if (result.result.failed_cancellations) {
          result.result.failed_cancellations.forEach((failure) => {
            results.errors.push({
              order_id: failure.order_id,
              error: failure.reason || "Unknown error",
            });
          });
        }

        processedCount += chunk.length;

        // Small delay between chunks
        if (i < chunks.length - 1) {
          await new Promise((resolve) => setTimeout(resolve, 500));
        }
      } catch (error) {
        console.error(`  ❌ Chunk ${i + 1} failed:`, error.message);

        // Mark all orders in this chunk as failed
        chunk.forEach((orderId) => {
          results.failed++;
          results.errors.push({
            order_id: orderId,
            error: error.message || "Chunk failed",
          });
        });

        processedCount += chunk.length;
      }
    }

    // Final status
    if (onProgress) {
      onProgress({
        status: "complete",
        total: orderIds.length,
        processed: orderIds.length,
        successful: results.successful,
        pending: results.pending,
        failed: results.failed,
        message: `Complete: ${results.successful} cancelled, ${results.pending} pending, ${results.failed} failed`,
      });
    }

    console.log("\n=== CANCELLATION SUMMARY ===");
    console.log(`✅ Successfully cancelled: ${results.successful}`);
    console.log(`⏳ Pending: ${results.pending}`);
    console.log(`❌ Failed: ${results.failed}`);
    console.log(`📊 Total: ${orderIds.length}`);

    return results;
  } catch (error) {
    console.error("❌ Bulk cancellation error:", error);
    throw error;
  }
}

// ============================================================================
// BULK LISTING - PARALLEL MODE (OPTIMIZED)
// ============================================================================

async function bulkListCards(listingDataArray, onProgress) {
  if (!isConnected || !orderbookSDK || !signer) {
    throw new Error("Please connect wallet first");
  }

  // Always use parallel mode with hardcoded key
  if (usePrivateKey) {
    console.log("🔥 Using AUTOMATED + PARALLEL mode - maximum speed!");
    return await bulkListParallel(listingDataArray, onProgress);
  }

  // Fallback for MetaMask users
  const totalCards = listingDataArray.length;
  const mode = confirm(
    `List ${totalCards} cards:\n\n` +
      `✅ YES = ⚡ PARALLEL MODE - FASTEST!\n` +
      `❌ NO = Standard (one by one)`
  );

  if (mode) {
    return await bulkListParallel(listingDataArray, onProgress);
  } else {
    return await bulkListStandard(listingDataArray, onProgress);
  }
}

async function bulkListParallel(listingDataArray, onProgress) {
  listingCancelled = false;
  currentListingAbortController = new AbortController();

  const results = {
    total: listingDataArray.length,
    successful: 0,
    failed: 0,
    cancelled: 0,
    errors: [],
    listings: [],
  };

  const PREPARE_BATCH_SIZE = 10;
  const PREPARE_DELAY = 500;
  const CREATE_BATCH_SIZE = 5;
  const CREATE_DELAY = 800;

  try {
    const preparedQueue = [];
    const signedQueue = [];
    let approvalDone = false;
    let preparingComplete = false;
    let signingComplete = false;

    // PIPELINE STAGE 1: PREPARE
    const preparePipeline = (async () => {
      if (onProgress) {
        onProgress({
          status: "preparing",
          total: listingDataArray.length,
          processed: 0,
          message: "⚡ Preparing listings...",
          showCancel: true,
        });
      }

      const totalBatches = Math.ceil(
        listingDataArray.length / PREPARE_BATCH_SIZE
      );

      for (let batchIndex = 0; batchIndex < totalBatches; batchIndex++) {
        if (listingCancelled) {
          console.log("🛑 Preparing cancelled by user");
          break;
        }

        const start = batchIndex * PREPARE_BATCH_SIZE;
        const end = Math.min(
          start + PREPARE_BATCH_SIZE,
          listingDataArray.length
        );
        const batch = listingDataArray.slice(start, end);

        const batchPromises = batch.map(async (cardData) => {
          if (listingCancelled) return null;

          try {
            const currencyAddress =
              cardData.currency_address ||
              "0x52a6c53869ce09a731cd772f245b97a4401d3348";

            const prepareResponse = await orderbookSDK.prepareListing({
              makerAddress: walletAddress,
              sell: {
                contractAddress: GU_CONTRACT_ADDRESS,
                tokenId: String(cardData.token_id),
                type: "ERC721",
              },
              buy: {
                type: "ERC20",
                contractAddress: currencyAddress,
                amount: cardData.listing_price_wei,
              },
            });

            // Handle approval
            for (const action of prepareResponse.actions) {
              if (action.type === "TRANSACTION" && !approvalDone) {
                console.log("🔥 Auto-approving NFT contract...");
                const tx = await signer.sendTransaction({
                  to: action.buildTransaction.to,
                  data: action.buildTransaction.data,
                });
                await tx.wait();
                approvalDone = true;
                console.log("✅ Approval done!");
              }
            }

            const signableAction = prepareResponse.actions.find(
              (a) => a.type === "SIGNABLE"
            );

            if (signableAction) {
              return {
                tokenId: cardData.token_id,
                orderComponents: prepareResponse.orderComponents,
                orderHash: prepareResponse.orderHash,
                signableAction: signableAction,
              };
            }
            return null;
          } catch (error) {
            console.error(`Failed to prepare ${cardData.token_id}:`, error);
            results.failed++;
            results.errors.push({
              token_id: cardData.token_id,
              error: error.message,
              stage: "preparation",
            });
            return null;
          }
        });

        const batchResults = await Promise.all(batchPromises);
        batchResults.forEach((result) => {
          if (result) preparedQueue.push(result);
        });

        if (onProgress) {
          onProgress({
            status: "preparing",
            total: listingDataArray.length,
            processed: end,
            message: `Prepared ${end}/${listingDataArray.length}...`,
            showCancel: true,
          });
        }

        if (!listingCancelled && batchIndex < totalBatches - 1) {
          await new Promise((resolve) => setTimeout(resolve, PREPARE_DELAY));
        }
      }

      preparingComplete = true;
      console.log(
        `✅ Preparing complete: ${preparedQueue.length} ready to sign`
      );
    })();

    // PIPELINE STAGE 2: SIGN
    const signingPipeline = (async () => {
      let signedCount = 0;

      while (!preparingComplete || preparedQueue.length > 0) {
        if (listingCancelled) {
          console.log("🛑 Signing cancelled by user");
          break;
        }

        if (preparedQueue.length === 0) {
          await new Promise((resolve) => setTimeout(resolve, 100));
          continue;
        }

        const listing = preparedQueue.shift();
        if (!listing) continue;

        if (onProgress) {
          onProgress({
            status: "signing",
            total: listingDataArray.length,
            processed: signedCount,
            message: `Signing ${signedCount + 1}/${
              preparedQueue.length + signedCount + 1
            }...`,
            showCancel: true,
          });
        }

        try {
          const signature = await signer.signTypedData(
            listing.signableAction.message.domain,
            listing.signableAction.message.types,
            listing.signableAction.message.value
          );

          signedQueue.push({
            ...listing,
            signature,
          });

          signedCount++;
        } catch (error) {
          console.error(`❌ Sign failed ${listing.tokenId}:`, error.message);
          results.failed++;
          results.errors.push({
            token_id: listing.tokenId,
            error: error.message,
            stage: "signing",
          });
        }
      }

      signingComplete = true;
      console.log(`✅ Signing complete: ${signedQueue.length} signed`);
    })();

    // PIPELINE STAGE 3: CREATE
    const createPipeline = (async () => {
      let createdCount = 0;

      while (!signingComplete || signedQueue.length > 0) {
        if (listingCancelled) {
          console.log("🛑 Creating cancelled by user");
          results.cancelled =
            listingDataArray.length - results.successful - results.failed;
          break;
        }

        if (signedQueue.length < CREATE_BATCH_SIZE && !signingComplete) {
          await new Promise((resolve) => setTimeout(resolve, 100));
          continue;
        }

        if (signedQueue.length === 0) {
          await new Promise((resolve) => setTimeout(resolve, 100));
          continue;
        }

        const batch = signedQueue.splice(0, CREATE_BATCH_SIZE);

        const createPromises = batch.map(async (cardData) => {
          if (listingCancelled) {
            return { cancelled: true, cardData };
          }

          const MAX_RETRIES = 3;
          for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
            try {
              const result = await orderbookSDK.createListing({
                makerFees: [],
                orderComponents: cardData.orderComponents,
                orderHash: cardData.orderHash,
                orderSignature: cardData.signature,
              });

              return { success: true, cardData, result: result.result };
            } catch (error) {
              if (attempt < MAX_RETRIES) {
                console.warn(
                  `⚠️ ${cardData.tokenId} retry ${attempt}/${MAX_RETRIES}`
                );
                await new Promise((resolve) =>
                  setTimeout(resolve, 1000 * attempt)
                );
              } else {
                console.error(
                  `❌ Create failed ${cardData.tokenId}:`,
                  error.message
                );
                return { success: false, cardData, error };
              }
            }
          }
        });

        const createBatchResults = await Promise.all(createPromises);

        for (const result of createBatchResults) {
          if (result.cancelled) {
            console.log(`🛑 Cancelled: ${result.cardData.tokenId}`);
          } else if (result.success) {
            results.successful++;
            results.listings.push({
              token_id: result.cardData.tokenId,
              listing_id: result.result.id,
              status: "success",
            });
            console.log(`✅ Listed token ${result.cardData.tokenId}`);
          } else {
            results.failed++;
            results.errors.push({
              token_id: result.cardData.tokenId,
              error: `Create: ${result.error.message}`,
            });
          }
        }

        createdCount += createBatchResults.length;

        if (onProgress) {
          onProgress({
            status: "creating",
            total: listingDataArray.length,
            processed: createdCount,
            message: `Creating... ${createdCount}/${listingDataArray.length}`,
            showCancel: true,
          });
        }

        if (!listingCancelled) {
          await new Promise((resolve) => setTimeout(resolve, CREATE_DELAY));
        }
      }

      console.log(`✅ All creating complete: ${results.successful} listed`);
    })();

    await Promise.all([preparePipeline, signingPipeline, createPipeline]);

    const finalStatus = listingCancelled ? "cancelled" : "complete";

    if (onProgress) {
      onProgress({
        status: finalStatus,
        total: listingDataArray.length,
        processed: listingDataArray.length,
        successful: results.successful,
        failed: results.failed,
        cancelled: results.cancelled,
        showCancel: false,
      });
    }

    if (listingCancelled) {
      console.log(
        `🛑 Listing cancelled: ${results.successful} listed, ${results.cancelled} cancelled, ${results.failed} failed`
      );
    } else {
      console.log(
        `🎉 Listing complete: ${results.successful} success, ${results.failed} failed`
      );
    }
  } catch (error) {
    if (error.message === "Listing cancelled by user") {
      console.log("🛑 Listing process cancelled");
      results.cancelled =
        listingDataArray.length - results.successful - results.failed;
    } else {
      console.error("❌ Listing error:", error);
      throw error;
    }
  } finally {
    listingCancelled = false;
    currentListingAbortController = null;
  }

  return results;
}

async function bulkListStandard(listingDataArray, onProgress) {
  const totalCards = listingDataArray.length;
  const batches = Math.ceil(totalCards / BATCH_SIZE);
  const results = {
    total: totalCards,
    successful: 0,
    failed: 0,
    errors: [],
    listings: [],
  };

  let approvalDone = false;

  for (let batchIndex = 0; batchIndex < batches; batchIndex++) {
    const start = batchIndex * BATCH_SIZE;
    const end = Math.min(start + BATCH_SIZE, totalCards);
    const batchData = listingDataArray.slice(start, end);

    if (onProgress) {
      onProgress({
        status: "processing",
        total: totalCards,
        processed: start,
        currentBatch: batchIndex + 1,
        totalBatches: batches,
      });
    }

    for (const cardData of batchData) {
      try {
        const currencyAddress =
          cardData.currency_address ||
          "0x52a6c53869ce09a731cd772f245b97a4401d3348";

        const prepareResponse = await orderbookSDK.prepareListing({
          makerAddress: walletAddress,
          sell: {
            contractAddress: GU_CONTRACT_ADDRESS,
            tokenId: String(cardData.token_id),
            type: "ERC721",
          },
          buy: {
            type: "ERC20",
            contractAddress: currencyAddress,
            amount: cardData.listing_price_wei,
          },
        });

        for (const action of prepareResponse.actions) {
          if (action.type === "TRANSACTION" && !approvalDone) {
            const tx = await signer.sendTransaction({
              to: action.buildTransaction.to,
              data: action.buildTransaction.data,
            });
            await tx.wait();
            approvalDone = true;
          }
        }

        const signableAction = prepareResponse.actions.find(
          (a) => a.type === "SIGNABLE"
        );

        if (signableAction) {
          const signature = await signer.signTypedData(
            signableAction.message.domain,
            signableAction.message.types,
            signableAction.message.value
          );

          const createResponse = await orderbookSDK.createListing({
            makerFees: [],
            orderComponents: prepareResponse.orderComponents,
            orderHash: prepareResponse.orderHash,
            orderSignature: signature,
          });

          results.successful++;
          results.listings.push({
            token_id: cardData.token_id,
            listing_id: createResponse.result.id,
            status: "success",
          });
        }
      } catch (error) {
        results.failed++;
        results.errors.push({
          token_id: cardData.token_id,
          error: error.message,
        });
      }
    }

    if (batchIndex < batches - 1) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }

  if (onProgress) {
    onProgress({
      status: "complete",
      total: totalCards,
      processed: totalCards,
      successful: results.successful,
      failed: results.failed,
    });
  }

  return results;
}

// ============================================================================
// EXPORTS
// ============================================================================

window.OrderbookIntegration = {
  initializeOrderbook,
  bulkListCards,
  bulkCancelListings,
  fetchZkevmListings,
  isConnected: () => isConnected,
  getWalletAddress: () => walletAddress,
  isAutomatedSigningEnabled: () => usePrivateKey,
  BATCH_SIZE,
};

console.log("✅ Orderbook Integration loaded (COMPLETE VERSION)");
console.log("🔥 Private key and publishable key are HARDCODED");
console.log("⚡ Bulk listing: Parallel pipelined mode");
console.log("🎯 Bulk cancellation: Proper Immutable SDK methods");
window.cancelListing = cancelCurrentListing;
